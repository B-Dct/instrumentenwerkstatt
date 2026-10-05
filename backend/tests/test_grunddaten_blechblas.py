"""Vorgabewerte für Blechblasinstrumente (Migration blechblas_vorgabewerte).

Das Grunddaten-Modul selbst schreibt in das Schema vom Oktober 2026 (Ausführung als Text am Richtpreis) und
läuft nur noch innerhalb der Migrationskette. Geprüft wird hier deshalb die Liste selbst und der Stand der
Datenbank nach allen Migrationen."""

from sqlalchemy import select

from app.einstellungen import wert
from app.grunddaten.blechblas_2026_10 import REPARATURARTEN, VORGABEWERTE
from app.models import Instrumentenklasse, Reparaturart, ReparaturVorgabewert


def test_die_liste_selbst_ist_vollstaendig():
    assert len(VORGABEWERTE) == 15 and list(REPARATURARTEN.items()) == [("Reinigung", 2), ("Überholung", 3)]
    assert sum(len(a) * 2 for a in VORGABEWERTE.values()) == 38
    # Nur Trompete und Flügelhorn/Kornett haben mehrere Ausführungen, jede Klasse hat eine Standardausführung
    assert {k: len(a) for k, a in VORGABEWERTE.items() if len(a) > 1} == {"Trompete": 4, "Flügelhorn/Kornett": 2}
    assert all(None in a for a in VORGABEWERTE.values())
    # Stunden passen zum Stundensatz: Preis ÷ 45, auf 0,25 gerundet
    for je_ausfuehrung in VORGABEWERTE.values():
        for werte in je_ausfuehrung.values():
            for stunden, euro in werte:
                assert float(stunden) == round(float(euro) / 45 * 4) / 4


def test_nach_den_migrationen_ist_alles_vorhanden(db):
    """Geprüft wird nur, was die Werkstatt nicht selbst pflegt: Preise, Ausführungen und der Stundensatz
    dürfen sich seit der Migration geändert haben."""
    klassen = db.scalars(select(Instrumentenklasse).where(Instrumentenklasse.bezeichnung.in_(VORGABEWERTE))).all()
    arten = db.scalars(select(Reparaturart).where(Reparaturart.bezeichnung.in_(REPARATURARTEN))).all()
    assert len(klassen) == 15 and len(arten) == 2
    assert db.scalar(select(ReparaturVorgabewert.id).where(
        ReparaturVorgabewert.instrumentenklasse_id.in_([k.id for k in klassen]),
        ReparaturVorgabewert.reparaturart_id.in_([r.id for r in arten])).limit(1)) is not None
    assert wert(db, "stundensatz") is not None
    # Keine Trompeten- oder Flügelhorn-Varianten als eigene Klassen
    varianten = db.scalars(select(Instrumentenklasse.bezeichnung).where(
        Instrumentenklasse.bezeichnung.like("Trompete (%") | Instrumentenklasse.bezeichnung.like("Flügelhorn%("))).all()
    assert varianten == []
