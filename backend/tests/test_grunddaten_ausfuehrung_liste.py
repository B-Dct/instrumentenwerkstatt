"""Übertragung der Ausführungen von Text auf die Liste je Instrumentenklasse (Migration ausfuehrung_als_liste).

Die Textspalten gibt es nach der Migration nicht mehr. Jeder Test legt sie deshalb für seine Dauer wieder an
(wird wie alles im Test zurückgerollt) und stellt mit eigenen TEST-Klassen den alten Stand nach."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.grunddaten.ausfuehrung_liste_2026_10 import NichtEindeutig, aehnlich, uebertragen
from app.models import Ausfuehrung, Instrument, Instrumentenklasse, Kunde, Reparaturart, ReparaturVorgabewert
from app.schaetzung import schaetze_arbeitsstunden, schaetze_kosten


class Altstand:
    """Legt Richtpreise und Instrumente so an, wie sie vor der Migration aussahen (Ausführung als Text)."""

    def __init__(self, db):
        self.db = db
        db.execute(text("ALTER TABLE reparatur_vorgabewert ADD COLUMN ausfuehrung varchar(100), "
                        "ADD COLUMN ist_standard boolean NOT NULL DEFAULT false"))
        db.execute(text("ALTER TABLE instrument ADD COLUMN ausfuehrung varchar(100)"))
        # Die Eindeutigkeit galt damals über den Text, nicht über den (noch leeren) Verweis
        db.execute(text("DROP INDEX uq_reparatur_vorgabewert_kombination"))
        self.reinigung = Reparaturart(bezeichnung="TEST Reinigung", standard_komplexitaet=2)
        self.ueberholung = Reparaturart(bezeichnung="TEST Überholung", standard_komplexitaet=3)
        self.kunde = Kunde(kundennummer="TEST-ALTSTAND", name="Test Kunde")
        db.add_all([self.reinigung, self.ueberholung, self.kunde])
        db.flush()

    def klasse(self, bezeichnung):
        klasse = Instrumentenklasse(bezeichnung=bezeichnung, oberkategorie="Test")
        self.db.add(klasse)
        self.db.flush()
        return klasse

    def wert(self, klasse, art, ausfuehrung, kosten, standard=False, archiviert=False):
        v = ReparaturVorgabewert(reparaturart_id=art.id, instrumentenklasse_id=klasse.id, vorgabe_stunden=Decimal("1.00"),
                                 vorgabe_kosten=Decimal(kosten), archiviert_am=datetime.now(timezone.utc) if archiviert else None)
        self.db.add(v)
        self.db.flush()
        self.db.execute(text("UPDATE reparatur_vorgabewert SET ausfuehrung = :a, ist_standard = :s WHERE id = :id"),
                        {"a": ausfuehrung, "s": standard, "id": v.id})
        return v

    def instrument(self, klasse, ausfuehrung):
        i = Instrument(kunde_id=self.kunde.id, instrumentenklasse_id=klasse.id)
        self.db.add(i)
        self.db.flush()
        self.db.execute(text("UPDATE instrument SET ausfuehrung = :a WHERE id = :id"), {"a": ausfuehrung, "id": i.id})
        return i

    def ausfuehrungen(self, klasse):
        self.db.expire_all()
        return {a.bezeichnung: a for a in self.db.scalars(select(Ausfuehrung).where(Ausfuehrung.instrumentenklasse_id == klasse.id))}

    def stand(self):
        """Alles, was die Übertragung anfassen könnte – zum Vergleich vor und nach einem erneuten Lauf."""
        self.db.expire_all()
        return (sorted((str(a.id), a.bezeichnung, a.ist_standard, a.archiviert_am) for a in self.db.scalars(select(Ausfuehrung))),
                sorted((str(v.id), str(v.ausfuehrung_id)) for v in self.db.scalars(select(ReparaturVorgabewert))),
                sorted((str(i.id), str(i.ausfuehrung_id)) for i in self.db.scalars(select(Instrument))))


@pytest.fixture
def alt(db):
    return Altstand(db)


def test_in_dieser_datenbank_ist_nichts_mehr_zu_tun(db, alt):
    """Die Migration ist bereits gelaufen: Für die echten Daten ändert ein weiterer Lauf nichts."""
    vorher = alt.stand()
    ergebnis = uebertragen(db.connection())
    assert {k: v for k, v in ergebnis.items() if k != "hinweise"} == {
        "ausfuehrungen": 0, "richtpreise": 0, "instrumente": 0, "dem_standard_zugeordnet": 0}
    assert alt.stand() == vorher


def test_uebertragung_laesst_schaetzung_und_instrumente_unveraendert_und_ist_wiederholbar(db, alt):
    trompete, tuba = alt.klasse("TEST Trompete"), alt.klasse("TEST Tuba")
    # Trompete: Standard "Perinet, lackiert" bei beiden Reparaturarten, dazu "Perinet, versilbert" in zwei Schreibweisen
    alt.wert(trompete, alt.reinigung, "Perinet, lackiert", "80.00", standard=True)
    alt.wert(trompete, alt.reinigung, "Perinet, versilbert", "155.00")
    alt.wert(trompete, alt.ueberholung, "Perinet, lackiert", "105.00", standard=True)
    alt.wert(trompete, alt.ueberholung, "perinet,  VERSILBERT ", "219.00")
    alt.wert(trompete, alt.reinigung, "vergoldet", "400.00", archiviert=True)          # gibt es nur noch archiviert
    # Tuba: Ausführungen nur bei der Reinigung; die Überholung hat einen einzigen Wert ohne Namen
    alt.wert(tuba, alt.reinigung, "Normal", "209.00", standard=True)
    alt.wert(tuba, alt.reinigung, "Aufwändig", "350.00")
    ohne_namen = alt.wert(tuba, alt.ueberholung, None, "300.00")
    einzeln = alt.klasse("TEST Horn")                                                  # Klasse ohne Ausführungen
    alt.wert(einzeln, alt.reinigung, None, "130.00")
    instrumente = {"versilbert": alt.instrument(trompete, "PERINET, versilbert"), "standard": alt.instrument(trompete, "Perinet, lackiert"),
                   "unbekannt": alt.instrument(trompete, None), "vergoldet": alt.instrument(trompete, "vergoldet"),
                   "horn": alt.instrument(einzeln, None)}

    ergebnis = uebertragen(db.connection())
    assert {k: v for k, v in ergebnis.items() if k != "hinweise"} == {
        "ausfuehrungen": 5, "richtpreise": 7, "instrumente": 3, "dem_standard_zugeordnet": 1}

    t, b = alt.ausfuehrungen(trompete), alt.ausfuehrungen(tuba)
    # Gleiche Bezeichnungen zusammengeführt, der bisherige Standard ist Standard der Klasse
    assert {n: (a.ist_standard, a.archiviert_am is None) for n, a in t.items()} == {
        "Perinet, lackiert": (True, True), "Perinet, versilbert": (False, True), "vergoldet": (False, False)}
    assert {n: a.ist_standard for n, a in b.items()} == {"Normal": True, "Aufwändig": False}
    assert alt.ausfuehrungen(einzeln) == {}
    # Der unbenannte Wert einer Klasse mit Ausführungen gehört zum Standard
    assert db.get(ReparaturVorgabewert, ohne_namen.id).ausfuehrung_id == b["Normal"].id

    # Instrumente: über den bisherigen Namen verknüpft, unbekannt bleibt unbekannt
    verknuepft = {name: db.get(Instrument, i.id).ausfuehrung_id for name, i in instrumente.items()}
    assert verknuepft == {"versilbert": t["Perinet, versilbert"].id, "standard": t["Perinet, lackiert"].id,
                          "unbekannt": None, "vergoldet": t["vergoldet"].id, "horn": None}

    # Schätzung wie vor der Übertragung (alte Regeln: benannte Ausführung, sonst Standard der Kombination)
    def kosten(klasse, art, ausfuehrung=None):
        k = schaetze_kosten(db, klasse.id, art.id, ausfuehrung.id if ausfuehrung else None)
        assert schaetze_arbeitsstunden(db, klasse.id, art.id, ausfuehrung.id if ausfuehrung else None).wert == Decimal("1.00")
        return k.wert
    assert kosten(trompete, alt.reinigung) == Decimal("80.00")                                   # unbekannt → Standard
    assert kosten(trompete, alt.reinigung, t["Perinet, versilbert"]) == Decimal("155.00")
    assert kosten(trompete, alt.ueberholung, t["Perinet, versilbert"]) == Decimal("219.00")      # andere Schreibweise, dieselbe Ausführung
    assert kosten(trompete, alt.ueberholung, t["Perinet, lackiert"]) == Decimal("105.00")
    assert kosten(trompete, alt.reinigung, t["vergoldet"]) == Decimal("80.00")                   # archiviert → Standard
    assert kosten(tuba, alt.reinigung) == Decimal("209.00") and kosten(tuba, alt.reinigung, b["Aufwändig"]) == Decimal("350.00")
    assert kosten(tuba, alt.ueberholung) == kosten(tuba, alt.ueberholung, b["Aufwändig"]) == Decimal("300.00")
    assert kosten(einzeln, alt.reinigung) == Decimal("130.00")

    # Zweiter Lauf: nichts ändert sich
    vorher = alt.stand()
    zweiter = uebertragen(db.connection())
    assert {k: v for k, v in zweiter.items() if k != "hinweise"} == {
        "ausfuehrungen": 0, "richtpreise": 0, "instrumente": 0, "dem_standard_zugeordnet": 0}
    assert alt.stand() == vorher


def test_abweichender_standard_wird_gemeldet_nicht_geraten(db, alt):
    klasse = alt.klasse("TEST Kornett")
    alt.wert(klasse, alt.reinigung, "lackiert", "80.00", standard=True)
    alt.wert(klasse, alt.reinigung, "versilbert", "150.00")
    alt.wert(klasse, alt.ueberholung, "lackiert", "100.00")
    alt.wert(klasse, alt.ueberholung, "versilbert", "200.00", standard=True)      # hier ist ein anderer der Standard
    vorher = alt.stand()
    with pytest.raises(NichtEindeutig) as fehler:
        uebertragen(db.connection())
    assert any("TEST Kornett" in p and "weicht" in p for p in fehler.value.probleme)
    assert alt.stand() == vorher                                                   # nichts wurde geändert


def test_fehlender_standard_wird_gemeldet_nicht_geraten(db, alt):
    klasse = alt.klasse("TEST Kornett")
    alt.wert(klasse, alt.reinigung, "lackiert", "80.00")
    alt.wert(klasse, alt.reinigung, "versilbert", "150.00")
    with pytest.raises(NichtEindeutig) as fehler:
        uebertragen(db.connection())
    assert any("TEST Kornett" in p and "keine ist als Standard" in p for p in fehler.value.probleme)
    assert alt.ausfuehrungen(klasse) == {}


def test_moegliche_tippfehler_werden_gemeldet_und_nicht_zusammengefuehrt(db, alt):
    klasse = alt.klasse("TEST Kornett")
    alt.wert(klasse, alt.reinigung, "Perinet, lackiert", "80.00", standard=True)
    alt.wert(klasse, alt.reinigung, "Perinet, lakiert", "81.00")                  # Tippfehler?
    alt.wert(klasse, alt.reinigung, "Drehventile, lackiert", "130.00")
    ergebnis = uebertragen(db.connection())
    assert len(alt.ausfuehrungen(klasse)) == 3                                     # nichts zusammengeführt
    assert [h for h in ergebnis["hinweise"] if "TEST Kornett" in h] == [
        "TEST Kornett: „Perinet, lackiert“ und „Perinet, lakiert“ unterscheiden sich kaum – Tippfehler?"]


def test_aehnlichkeit():
    assert aehnlich("Perinet, lackiert", "Perinet lackiert") and aehnlich("versilbert", "versilbet")
    assert not aehnlich("Perinet, lackiert", "perinet,  LACKIERT")                 # das ist dieselbe Bezeichnung
    assert not aehnlich("Perinet, lackiert", "Perinet, versilbert") and not aehnlich("Normal", "Aufwändig")
