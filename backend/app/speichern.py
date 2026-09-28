"""Zentraler Baustein: speichern, bei Verletzung einer Datenbankregel sauber zurücknehmen und
eine verständliche Meldung liefern.

Verwendung – ALLE Änderungen, die eine Regel verletzen könnten, gehören in den Block:

    with sicher_speichern(db):
        db.add(neuer_eintrag)          # neue Datensätze
        eintrag.bezeichnung = "…"      # Feldänderungen
    # hier ist gespeichert (geflusht) – oder es wurde HTTP 409 mit Meldung ausgelöst

Warum im Block: Scheitert das Speichern, nimmt der Speicherpunkt genau diese Änderungen
zurück. Wurde eine Änderung VOR dem Block gesetzt, bliebe sie in der Sitzung hängen und würde
beim nächsten Speichern erneut versucht (Fehlerbild, das dreimal aufgetreten ist).

Nirgendwo sonst IntegrityError abfangen oder begin_nested verwenden – das prüft ein Test
(tests/test_speichern.py). Was ohne diesen Baustein durchrutscht, fängt main.py als Sicherheitsnetz
ab (ebenfalls 409 mit Meldung statt 500); die Sitzung der Anfrage wird dann verworfen.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Deutsche Meldung je Eindeutigkeitsregel der Datenbank. Jede Regel MUSS hier stehen
# (ein Test gleicht das mit dem Datenmodell ab).
KONFLIKT_MELDUNGEN: dict[str, str] = {
    "uq_instrumentenklasse_bezeichnung":
        "Eine Instrumentenklasse mit dieser Bezeichnung gibt es bereits (ggf. archiviert – dann reaktivieren)",
    "uq_reparaturart_bezeichnung":
        "Eine Reparaturart mit dieser Bezeichnung gibt es bereits (ggf. archiviert – dann reaktivieren)",
    "uq_reparatur_vorgabewert_kombination":
        "Für diese Kombination aus Reparaturart und Instrumentenklasse gibt es bereits einen aktiven "
        "Vorgabewert – bitte den bestehenden bearbeiten",
    "uq_kunde_kundennummer": "Diese Kundennummer ist bereits vergeben",
    "uq_mitarbeiter_email": "Diese E-Mail-Adresse ist bereits einem Mitarbeiter-Konto zugeordnet",
    "uq_auftragsstatus_schluessel": "Diesen Status-Schlüssel gibt es bereits",
    "uq_auftragsstatus_bezeichnung": "Einen Status mit dieser Bezeichnung gibt es bereits",
    "uq_auftrag_auftragsnummer": "Diese Auftragsnummer ist bereits vergeben – bitte erneut versuchen",
    "uq_auftrag_zugriffstoken": "Der erzeugte Zugangscode war bereits vergeben – bitte erneut versuchen",
    "uq_unterbrechung_offen_je_auftrag": "Für diesen Auftrag läuft bereits eine Unterbrechung",
    "uq_mitarbeiter_arbeitszeit_aktuell":
        "Für diesen Mitarbeiter wurden gerade gleichzeitig Wochenstunden festgelegt – bitte neu laden",
}

ALLGEMEINE_MELDUNG = "Speichern nicht möglich: Die Eingabe widerspricht einer Datenregel"


def regelname(fehler: IntegrityError) -> str | None:
    diag = getattr(fehler.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def konflikt_meldung(fehler: IntegrityError, meldungen: dict[str, str] | None = None) -> str:
    """Meldung zur verletzten Regel: erst die aufruferspezifische, dann die zentrale."""
    name = regelname(fehler)
    return (meldungen or {}).get(name) or KONFLIKT_MELDUNGEN.get(name) or ALLGEMEINE_MELDUNG


@contextmanager
def sicher_speichern(db: Session, meldungen: dict[str, str] | None = None) -> Iterator[None]:
    """Führt die Änderungen im Block in einem Speicherpunkt aus und speichert (flush).

    Bei Verletzung einer Datenbankregel: nur diese Änderungen zurücknehmen (die Sitzung bleibt
    nutzbar) und HTTP 409 mit verständlicher Meldung auslösen. `meldungen` erlaubt eine
    passendere Meldung für einzelne Regeln in diesem Zusammenhang.
    """
    try:
        with db.begin_nested():
            yield
            db.flush()
    except IntegrityError as fehler:
        raise HTTPException(status.HTTP_409_CONFLICT, konflikt_meldung(fehler, meldungen)) from fehler
