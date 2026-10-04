"""Vorgabewerte für Blechblasinstrumente (Migration blechblas_vorgabewerte): vollständig, ohne Doppelte, überschreibt nichts."""

from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.einstellungen import wert
from app.grunddaten.blechblas_2026_10 import OBERKATEGORIE, REPARATURARTEN, VORGABEWERTE, anlegen
from app.models import Einstellung, Instrumentenklasse, Reparaturart, ReparaturVorgabewert
from app.schaetzung import Quelle, ausfuehrungen, schaetze_arbeitsstunden, schaetze_kosten

NEUE_KLASSEN = [k for k in VORGABEWERTE if k != "Trompete"]  # "Trompete" gab es schon vorher
FRISCH = {"reparaturarten": 2, "instrumentenklassen": 14, "vorgabewerte": 38, "einstellungen": 1}


def klassen(db):
    return {k.bezeichnung: k for k in db.scalars(select(Instrumentenklasse).where(Instrumentenklasse.bezeichnung.in_(VORGABEWERTE)))}


def arten(db):
    return {r.bezeichnung: r for r in db.scalars(select(Reparaturart).where(Reparaturart.bezeichnung.in_(REPARATURARTEN)))}


def vorgabewerte(db):
    return db.scalars(select(ReparaturVorgabewert).where(
        ReparaturVorgabewert.reparaturart_id.in_([r.id for r in arten(db).values()]),
        ReparaturVorgabewert.instrumentenklasse_id.in_([k.id for k in klassen(db).values()]),
    )).all()


def vorgabe(db, klasse, art, ausfuehrung=None):
    return db.scalar(select(ReparaturVorgabewert).where(
        ReparaturVorgabewert.instrumentenklasse_id == klassen(db)[klasse].id,
        ReparaturVorgabewert.reparaturart_id == arten(db)[art].id,
        ReparaturVorgabewert.ausfuehrung.is_not_distinct_from(ausfuehrung)))


@pytest.fixture
def leer(db):
    """Zustand vor der Migration nachstellen (wird wie alles im Test zurückgerollt): die neuen Klassen,
    Reparaturarten, Vorgabewerte und der Stundensatz fehlen; die Klasse "Trompete" gibt es schon."""
    db.execute(delete(ReparaturVorgabewert).where(ReparaturVorgabewert.id.in_([v.id for v in vorgabewerte(db)])))
    db.execute(delete(Instrumentenklasse).where(Instrumentenklasse.bezeichnung.in_(NEUE_KLASSEN)))
    db.execute(delete(Reparaturart).where(Reparaturart.bezeichnung.in_(REPARATURARTEN)))
    db.execute(delete(Einstellung).where(Einstellung.schluessel == "stundensatz"))
    db.flush()
    db.expire_all()
    assert "Trompete" in klassen(db)


def test_die_liste_selbst_ist_vollstaendig():
    assert len(VORGABEWERTE) == 15 and list(REPARATURARTEN.items()) == [("Reinigung", 2), ("Überholung", 3)]
    assert sum(len(a) * 2 for a in VORGABEWERTE.values()) == 38
    # Nur Trompete und Flügelhorn/Kornett haben mehrere Ausführungen, jede Klasse hat eine Standardausführung
    assert {k: len(a) for k, a in VORGABEWERTE.items() if len(a) > 1} == {"Trompete": 4, "Flügelhorn/Kornett": 2}
    assert all(None in a for a in VORGABEWERTE.values())


def test_nach_der_migration_ist_alles_vorhanden(db):
    """Die Migration ist in dieser Datenbank bereits gelaufen. Geprüft wird nur, was die Werkstatt nicht
    selbst pflegt: Preise, Ausführungen und der Stundensatz dürfen sich seit der Migration geändert haben."""
    assert len(klassen(db)) == 15 and len(arten(db)) == 2 and len(vorgabewerte(db)) > 0
    assert wert(db, "stundensatz") is not None
    # Keine Trompeten- oder Flügelhorn-Varianten als eigene Klassen
    varianten = db.scalars(select(Instrumentenklasse.bezeichnung).where(
        Instrumentenklasse.bezeichnung.like("Trompete (%") | Instrumentenklasse.bezeichnung.like("Flügelhorn%("))).all()
    assert varianten == []


def test_anlegen_auf_leerem_stand(db, leer):
    assert anlegen(db.connection()) == FRISCH
    assert all(klassen(db)[k].oberkategorie == OBERKATEGORIE and klassen(db)[k].archiviert_am is None for k in NEUE_KLASSEN)
    assert {r.bezeichnung: r.standard_komplexitaet for r in arten(db).values()} == {"Reinigung": 2, "Überholung": 3}
    assert wert(db, "stundensatz") == "45"

    # Stichproben aus der Tabelle (ohne Ausführung = Standard)
    for klasse, art, stunden, euro in [
        ("Doppelhorn", "Reinigung", "3.75", "169"),
        ("F-Tuba (5/6 Ventile)", "Überholung", "8.25", "369"),
        ("B-Tuba (3 Ventile)", "Überholung", "6.75", "300"),
        ("Tenorposaune mit Quartventil", "Reinigung", "2.50", "109"),
    ]:
        v = vorgabe(db, klasse, art)
        assert (v.vorgabe_stunden, v.vorgabe_kosten, v.ausfuehrung) == (Decimal(stunden), Decimal(euro), None), (klasse, art)
        assert "Reisser Musik" in v.notiz and "ab“-Preis" not in v.notiz
    # Posaunen: Überholung nur als "ab"-Preis
    for posaune in ("Tenorposaune", "Tenorposaune mit Quartventil", "Bassposaune (2 Ventile)"):
        v = vorgabe(db, posaune, "Überholung")
        assert (v.vorgabe_stunden, v.vorgabe_kosten) == (Decimal("1.00"), Decimal("45")) and "„ab“-Preis" in v.notiz
    # Stunden passen zum Stundensatz: Preis ÷ 45, auf 0,25 gerundet
    for v in vorgabewerte(db):
        assert v.vorgabe_stunden == round(v.vorgabe_kosten / 45 * 4) / Decimal(4), v.notiz


def test_trompete_eine_klasse_mit_vier_ausfuehrungen(db, leer):
    anlegen(db.connection())
    erwartet = {  # Ausführung → (Reinigung Std., €, Überholung Std., €)
        None: ("1.75", "80", "2.25", "105"),
        "Perinet, versilbert": ("3.50", "155", "4.75", "219"),
        "Drehventile, lackiert": ("3.00", "130", "4.00", "185"),
        "Drehventile, versilbert": ("3.75", "165", "5.50", "250"),
    }
    for art in ("Reinigung", "Überholung"):
        assert [a.ausfuehrung for a in ausfuehrungen(db, arten(db)[art].id, klassen(db)["Trompete"].id)] == \
            [None, "Drehventile, lackiert", "Drehventile, versilbert", "Perinet, versilbert"]  # Standard zuerst
    for ausfuehrung, (r_std, r_eur, u_std, u_eur) in erwartet.items():
        r, u = vorgabe(db, "Trompete", "Reinigung", ausfuehrung), vorgabe(db, "Trompete", "Überholung", ausfuehrung)
        assert (r.vorgabe_stunden, r.vorgabe_kosten) == (Decimal(r_std), Decimal(r_eur)), ausfuehrung
        assert (u.vorgabe_stunden, u.vorgabe_kosten) == (Decimal(u_std), Decimal(u_eur)), ausfuehrung
    assert "Standardausführung: Perinet, lackiert" in vorgabe(db, "Trompete", "Reinigung").notiz
    assert db.scalar(select(func.count()).select_from(Instrumentenklasse).where(Instrumentenklasse.bezeichnung.like("Trompete%"))) == 1


def test_fluegelhorn_kornett_eine_klasse_mit_zwei_ausfuehrungen(db, leer):
    anlegen(db.connection())
    kornett = klassen(db)["Flügelhorn/Kornett"]
    assert [a.ausfuehrung for a in ausfuehrungen(db, arten(db)["Reinigung"].id, kornett.id)] == [None, "Drehventile, lackiert"]
    assert vorgabe(db, "Flügelhorn/Kornett", "Überholung", "Drehventile, lackiert").vorgabe_kosten == Decimal("185")
    assert vorgabe(db, "Flügelhorn/Kornett", "Überholung").vorgabe_kosten == Decimal("105")
    assert db.scalar(select(func.count()).select_from(Instrumentenklasse).where(Instrumentenklasse.bezeichnung.like("Flügelhorn%"))) == 1


def test_erneuter_lauf_legt_nichts_doppelt_an(db, leer):
    anlegen(db.connection())
    assert anlegen(db.connection()) == {"reparaturarten": 0, "instrumentenklassen": 0, "vorgabewerte": 0, "einstellungen": 0}
    assert len(klassen(db)) == 15 and len(vorgabewerte(db)) == 38
    assert db.scalar(select(func.count()).select_from(Einstellung).where(Einstellung.schluessel == "stundensatz")) == 1


def test_erneuter_lauf_ueberschreibt_keine_anpassungen(db, leer):
    anlegen(db.connection())
    db.expire_all()
    geaendert, archiviert = vorgabe(db, "Trompete", "Reinigung", "Perinet, versilbert"), vorgabe(db, "Waldhorn", "Reinigung")
    geaendert.vorgabe_kosten = Decimal("999.00")
    archiviert.archiviert_am = func.clock_timestamp()
    db.scalar(select(Einstellung).where(Einstellung.schluessel == "stundensatz")).wert = "52"
    db.flush()

    assert sum(anlegen(db.connection()).values()) == 0
    db.expire_all()
    assert db.get(ReparaturVorgabewert, geaendert.id).vorgabe_kosten == Decimal("999.00")
    assert db.get(ReparaturVorgabewert, archiviert.id).archiviert_am is not None and len(vorgabewerte(db)) == 38
    assert wert(db, "stundensatz") == "52"


def test_schaetzung_nach_ausfuehrung(db, leer):
    anlegen(db.connection())
    trompete, tuba, reinigung = klassen(db)["Trompete"], klassen(db)["B-Tuba (4 Ventile)"], arten(db)["Reinigung"]

    def schaetzung(klasse, ausfuehrung=None):
        s, k = schaetze_arbeitsstunden(db, klasse.id, reinigung.id, ausfuehrung), schaetze_kosten(db, klasse.id, reinigung.id, ausfuehrung)
        assert s.quelle == k.quelle == Quelle.vorgabe_instrumentenklasse
        return s.wert, k.wert

    assert schaetzung(tuba) == (Decimal("5.00"), Decimal("225.00"))
    assert schaetzung(trompete) == (Decimal("1.75"), Decimal("80.00"))                              # ohne Auswahl: Standard
    assert schaetzung(trompete, "Drehventile, versilbert") == (Decimal("3.75"), Decimal("165.00"))
    assert schaetzung(trompete, "gibt es nicht") == (Decimal("1.75"), Decimal("80.00"))             # passt keine: Standard
    assert schaetzung(tuba, "Perinet, versilbert") == (Decimal("5.00"), Decimal("225.00"))          # Klasse ohne Varianten
