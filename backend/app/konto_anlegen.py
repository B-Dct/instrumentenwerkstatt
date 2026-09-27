"""Mitarbeiter-Konto über die Kommandozeile anlegen – vor allem für den allerersten Admin.

Ohne bestehenden Admin kann sonst niemand Konten anlegen (Henne-Ei-Problem).
Wer dieses Skript ausführen kann, hat ohnehin Zugriff auf .env und Datenbank.

Aufruf (im Ordner backend):
    uv run python -m app.konto_anlegen --email chefin@werkstatt.de --name "Anna Beispiel"
    uv run python -m app.konto_anlegen --email max@werkstatt.de --name "Max" --rolle mitarbeiter

Das Passwort wird verdeckt abgefragt (nicht als Parameter, damit es nicht in der
Shell-Historie landet).
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth import email_normalisieren, passwort_hashen
from app.db import SessionLocal
from app.models import Mitarbeiter, Systemrolle

MINDESTLAENGE_PASSWORT = 12


def passwort_abfragen() -> str:
    while True:
        passwort = getpass.getpass(f"Passwort (mind. {MINDESTLAENGE_PASSWORT} Zeichen): ")
        if len(passwort) < MINDESTLAENGE_PASSWORT:
            print(f"Zu kurz – bitte mindestens {MINDESTLAENGE_PASSWORT} Zeichen.")
            continue
        if getpass.getpass("Passwort wiederholen: ") != passwort:
            print("Die Passwörter stimmen nicht überein.")
            continue
        return passwort


def main() -> int:
    parser = argparse.ArgumentParser(description="Mitarbeiter-Konto anlegen (z. B. den ersten Admin)")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--rolle", choices=[r.value for r in Systemrolle], default=Systemrolle.admin.value,
                        help="Systemrolle (Standard: admin)")
    parser.add_argument("--fachrolle", help='Fachliche Rolle, z. B. "Geigenbauerin"')
    args = parser.parse_args()

    email = email_normalisieren(args.email)
    with SessionLocal() as db:
        if db.scalar(select(Mitarbeiter).where(Mitarbeiter.email == email)) is not None:
            print(f"Es gibt bereits ein Konto mit {email}.", file=sys.stderr)
            return 1

        passwort = passwort_abfragen()
        mitarbeiter = Mitarbeiter(
            name=args.name.strip(),
            email=email,
            rolle=args.fachrolle,
            systemrolle=Systemrolle(args.rolle),
            passwort_hash=passwort_hashen(passwort),
        )
        db.add(mitarbeiter)
        db.commit()
        print(f"Konto angelegt: {mitarbeiter.name} <{email}>, Systemrolle {args.rolle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
