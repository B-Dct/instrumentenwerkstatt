"""Umstellung der Bestandsdaten auf benannte Standardausführungen (Migration vorgabewert_ist_standard):
wiederholbar, ohne Daten zu verändern, und ohne zu raten."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.grunddaten.ausfuehrung_standard_2026_10 import NOTIZ_HINWEIS, PERINET_LACKIERT, anwenden
from app.models import Instrument, Instrumentenklasse, Kunde, Reparaturart, ReparaturVorgabewert


def _klasse(db, bezeichnung):
    return db.scalar(select(Instrumentenklasse).where(Instrumentenklasse.bezeichnung == bezeichnung))


def _werte(db, klasse, art=None):
    abfrage = select(ReparaturVorgabewert).where(ReparaturVorgabewert.instrumentenklasse_id == klasse.id,
                                                 ReparaturVorgabewert.archiviert_am.is_(None))
    if art is not None:
        abfrage = abfrage.where(ReparaturVorgabewert.reparaturart_id == art.id)
    return db.scalars(abfrage.order_by(ReparaturVorgabewert.reparaturart_id, ReparaturVorgabewert.ausfuehrung)).all()


def _stand(db):
    """Alle Richtpreise, wie sie gerade sind – zum Vergleich vor und nach einem erneuten Lauf."""
    db.expire_all()
    return sorted((str(v.id), v.ausfuehrung, v.ist_standard, v.notiz, v.vorgabe_kosten, v.vorgabe_stunden, v.archiviert_am)
                  for v in db.scalars(select(ReparaturVorgabewert)))


@pytest.fixture
def altstand(db):
    """Zustand vor der Migration nachstellen (wird zurückgerollt): Bei der Trompete ist der Standard wieder
    der Wert ohne Namen mit dem Hinweis in der Notiz, kein Wert trägt ein Kennzeichen."""
    trompete = _klasse(db, "Trompete")
    for v in db.scalars(select(ReparaturVorgabewert)):
        if v.instrumentenklasse_id == trompete.id and v.ausfuehrung == PERINET_LACKIERT:
            v.ausfuehrung, v.notiz = None, NOTIZ_HINWEIS + (v.notiz or "")
        v.ist_standard = False
    db.flush()
    art = Reparaturart(bezeichnung="TEST Politur", standard_komplexitaet=1)
    unklar = Instrumentenklasse(bezeichnung="TEST Unklar", oberkategorie="Test")
    einzeln = Instrumentenklasse(bezeichnung="TEST Einzeln", oberkategorie="Test")
    db.add_all([art, unklar, einzeln])
    db.flush()
    for klasse, ausfuehrung in [(unklar, "matt"), (unklar, "glänzend"), (einzeln, "matt")]:
        db.add(ReparaturVorgabewert(reparaturart_id=art.id, instrumentenklasse_id=klasse.id, ausfuehrung=ausfuehrung,
                                    vorgabe_stunden=Decimal("1.00"), vorgabe_kosten=Decimal("45.00")))
    db.flush()
    return {"trompete": trompete, "art": art, "unklar": unklar, "einzeln": einzeln}


def test_in_dieser_datenbank_ist_nichts_mehr_zu_tun(db):
    """Die Migration ist bereits gelaufen: Ein weiterer Lauf ändert nichts."""
    vorher = _stand(db)
    ergebnis = anwenden(db.connection())
    assert (ergebnis["benannt"], ergebnis["standard_gesetzt"]) == (0, 0)
    assert _stand(db) == vorher


def test_umstellung_benennt_den_standard_und_ist_wiederholbar(db, altstand):
    trompete = altstand["trompete"]
    kombinationen = {v.reparaturart_id for v in _werte(db, trompete) if v.ausfuehrung is None}
    assert kombinationen, "Vorbedingung: Die Trompete hat unbenannte Standardwerte"
    kunde = Kunde(kundennummer="TEST-STANDARD", name="Test Kunde")
    db.add(kunde)
    db.flush()
    unbekannt = Instrument(kunde_id=kunde.id, instrumentenklasse_id=trompete.id)
    db.add(unbekannt)
    db.flush()

    ergebnis = anwenden(db.connection())
    db.expire_all()
    assert ergebnis["benannt"] >= len(kombinationen)
    for v in _werte(db, trompete):
        if v.reparaturart_id in kombinationen:
            assert v.ausfuehrung is not None                                   # kein Wert mehr ohne Namen
            assert v.ist_standard == (v.ausfuehrung == PERINET_LACKIERT)
            assert NOTIZ_HINWEIS.strip() not in (v.notiz or "")                # der Hinweis steckt jetzt im Namen
    # Instrumente mit leerer Ausführung bleiben "unbekannt" und werden nicht umgeschrieben
    assert db.get(Instrument, unbekannt.id).ausfuehrung is None

    # Zweiter Lauf: nichts ändert sich
    vorher = _stand(db)
    zweiter = anwenden(db.connection())
    assert (zweiter["benannt"], zweiter["standard_gesetzt"]) == (0, 0) and _stand(db) == vorher
    assert zweiter["offen"] == ergebnis["offen"]


def test_umstellung_raet_nicht(db, altstand):
    ergebnis = anwenden(db.connection())
    db.expire_all()
    # Mehrere benannte Ausführungen ohne erkennbaren Standard: gemeldet, nicht verändert
    assert ("TEST Unklar", "TEST Politur") in ergebnis["offen"]
    assert [v.ist_standard for v in _werte(db, altstand["unklar"])] == [False, False]
    # Eine einzelne benannte Ausführung ist zwangsläufig der Standard
    assert [(v.ausfuehrung, v.ist_standard) for v in _werte(db, altstand["einzeln"])] == [("matt", True)]
    assert ("TEST Einzeln", "TEST Politur") not in ergebnis["offen"]
