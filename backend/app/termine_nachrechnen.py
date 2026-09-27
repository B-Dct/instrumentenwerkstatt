"""Fertigstellungstermine für offene Aufträge (nach)berechnen.

Gedacht für Aufträge, die vor Einführung der Terminschätzung angelegt wurden, oder um nach
Änderungen (z. B. neue Abwesenheiten, geänderte Wochenstunden) alle Termine aufzufrischen.
Jede Berechnung wird wie üblich im schaetzungs_log protokolliert (Anlass "nachberechnet").

Aufruf (im Ordner backend):
    uv run python -m app.termine_nachrechnen --probelauf   # nur anzeigen, nichts speichern
    uv run python -m app.termine_nachrechnen               # offene Aufträge OHNE Termin
    uv run python -m app.termine_nachrechnen --alle        # alle offenen Aufträge neu
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Auftrag, Auftragsstatus
from app.terminschaetzung import schaetze_fertigstellung, termin_neu_berechnen

ANLASS = "nachberechnet"


def nachrechnen(db: Session, alle: bool = False, probelauf: bool = False) -> list[tuple[str, str]]:
    """Liefert (Auftragsnummer, Ergebnis) je betrachtetem Auftrag."""
    abfrage = (
        select(Auftrag)
        .join(Auftragsstatus, Auftrag.status_aktuell_id == Auftragsstatus.id)
        .where(Auftragsstatus.ist_abgeschlossen.is_(False))
        .order_by(Auftrag.auftragsnummer)
    )
    if not alle:
        abfrage = abfrage.where(Auftrag.geschaetztes_fertigstellungsdatum.is_(None))

    ergebnis = []
    for auftrag in db.scalars(abfrage).all():
        if auftrag.geschaetzte_arbeitsstunden is None:
            # Ohne Stunden kein Termin – nicht protokollieren, sonst entstünde bei jedem Lauf ein Eintrag
            ergebnis.append((auftrag.auftragsnummer, "übersprungen: keine geschätzten Arbeitsstunden"))
            continue
        termin = (schaetze_fertigstellung(db, auftrag) if probelauf
                  else termin_neu_berechnen(db, auftrag, ANLASS))
        text = termin.datum.strftime("%d.%m.%Y") if termin.datum else "keine Schätzung möglich"
        if termin.bandbreite_von:
            text += f" (zwischen {termin.bandbreite_von:%d.%m.%Y} und {termin.bandbreite_bis:%d.%m.%Y})"
        ergebnis.append((auftrag.auftragsnummer, text))
    if not probelauf:
        db.commit()
    return ergebnis


def main() -> int:
    parser = argparse.ArgumentParser(description="Fertigstellungstermine offener Aufträge berechnen")
    parser.add_argument("--alle", action="store_true", help="auch Aufträge, die schon einen Termin haben")
    parser.add_argument("--probelauf", action="store_true", help="nur anzeigen, nichts speichern")
    args = parser.parse_args()
    with SessionLocal() as db:
        ergebnis = nachrechnen(db, alle=args.alle, probelauf=args.probelauf)
    if not ergebnis:
        print("Keine passenden offenen Aufträge.")
    for nummer, text in ergebnis:
        print(f"  {nummer}: {text}")
    if args.probelauf:
        print("Probelauf – nichts gespeichert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
