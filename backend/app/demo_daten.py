"""Beispieldaten zum Ausprobieren über /docs.

Aufruf (im Ordner backend):
    uv run python -m app.demo_daten anlegen     # legt an (mehrfach aufrufbar, nichts doppelt)
    uv run python -m app.demo_daten anzeigen    # zeigt IDs und Beispiel-Anfragen erneut
    uv run python -m app.demo_daten entfernen   # entfernt Demo-Kunden samt Instrumenten und Aufträgen

Angelegt werden:
- Stammdaten (2.4 Instrumentenklassen, 2.6 Reparaturarten, 2.6a Vorgabewerte). Die sind
  realistisch und bleiben beim Entfernen erhalten – sie können auch echt genutzt werden.
- Demo-Kunden (Kundennummer "DEMO-…") mit Instrumenten (2.1, 2.5)
- Vier offene Demo-Aufträge in verschiedenen Status (einer mit hoher Priorität, einer
  überfällig), um Statusdarstellung und Markierungen zu sehen
- Fünf abgeschlossene Demo-Aufträge "Saitenwechsel an Violine" (Nummer "DEMO-…") mit
  Arbeitszeit und Kosten. Damit greift für diese Kombination die historische Schätzung
  (ab 5 Vergleichsfällen) statt des Vorgabewerts – so sieht man beide Wege.
- Ein Demo-Mitarbeiter "Demo Geigenbauer" (nur als Bearbeiter der Demo-Aufträge; das
  Passwort ist zufällig und unbekannt, ein Login ist damit nicht möglich).
"""

import argparse
import secrets
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import passwort_hashen
from app.db import SessionLocal
from app.models import (
    Arbeitszeiterfassung,
    Auftrag,
    Auftragsstatus,
    AuftragStatusverlauf,
    Instrument,
    Instrumentenklasse,
    Kunde,
    Mitarbeiter,
    Reparaturart,
    ReparaturVorgabewert,
    SchaetzungsLog,
    SystemEreignisLog,
    Unterbrechung,
)

DEMO_PRAEFIX = "DEMO-"
DEMO_MITARBEITER_EMAIL = "demo-geigenbauer@beispiel.invalid"

INSTRUMENTENKLASSEN = [
    ("Violine", "Streichinstrument"),
    ("Violoncello", "Streichinstrument"),
    ("Gitarre", "Zupfinstrument"),
    ("Trompete", "Blechblasinstrument"),
    ("Klarinette", "Holzblasinstrument"),
    ("Klavier", "Tasteninstrument"),
]

REPARATURARTEN = [  # (Bezeichnung, Standard-Komplexität 1–5)
    ("Saitenwechsel", 1),
    ("Stimmen", 2),
    ("Ventil-Überholung", 3),
    ("Polster erneuern", 3),
    ("Rissreparatur Decke", 4),
    ("Generalüberholung", 5),  # bewusst ohne Vorgabewert → "keine Schätzung möglich"
]

VORGABEWERTE = [  # (Reparaturart, Instrumentenklasse oder None = allgemein, Stunden, Euro, Notiz)
    ("Saitenwechsel", None, "0.50", "25.00", "inkl. Standardsaiten"),
    ("Saitenwechsel", "Violoncello", "1.00", "45.00", "inkl. Standardsaiten, Cello-Saiten teurer"),
    ("Stimmen", None, "1.50", "90.00", None),
    ("Stimmen", "Klavier", "2.00", "120.00", "Hausbesuch nicht enthalten"),
    ("Ventil-Überholung", None, "2.50", "140.00", None),
    ("Polster erneuern", None, "3.00", "160.00", "kompletter Polstersatz"),
    ("Rissreparatur Decke", None, "4.00", "280.00", None),
    ("Rissreparatur Decke", "Violoncello", "6.00", "420.00", "größere Fläche"),
]

KUNDEN = [  # (Kundennummer, Name, E-Mail, Telefon, [(Klasse, Hersteller, Typ, Baujahr, Seriennummer)])
    ("DEMO-001", "Marie Schneider", "marie.schneider@example.com", "0151 0000001", [
        ("Violine", "Höfner", "H11", 2012, "HV-48213"),
        ("Gitarre", "Yamaha", "C40", 2019, None),
    ]),
    ("DEMO-002", "Jonas Weber", "jonas.weber@example.com", None, [
        ("Trompete", "Yamaha", "YTR-2330", 2016, "T-330981"),
        ("Klarinette", "Buffet Crampon", "E11", 2008, "E11-77120"),
    ]),
    ("DEMO-003", "Musikschule Lindenhof", "verwaltung.lindenhof@example.com", "030 0000003", [
        ("Violoncello", "Gewa", "Ideale", 2015, None),
        ("Klavier", "Yamaha", "U1", 1998, "U1-3312045"),
    ]),
]

# Offene Demo-Aufträge in verschiedenen Status (zeigen Statusfarben, Priorität, "überfällig"):
# (Nummer, Kunde, Instrumentenklasse, Reparaturart, Status, Priorität, vor wie vielen Tagen,
#  voraussichtlich fertig in Tagen – negativ = überfällig)
OFFENE_AUFTRAEGE = [
    ("DEMO-0101", "DEMO-002", "Trompete", "Ventil-Überholung", "angenommen", "hoch", 1, 6),
    ("DEMO-0102", "DEMO-003", "Violoncello", "Rissreparatur Decke", "in_bearbeitung", "normal", 9, 5),
    ("DEMO-0103", "DEMO-002", "Klarinette", "Polster erneuern", "wartet_auf_ersatzteil", "normal", 21, -3),
    ("DEMO-0104", "DEMO-003", "Klavier", "Stimmen", "qualitaetspruefung", "normal", 4, 1),
]

# Historie: Saitenwechsel an Violinen der Musikschule, (Minuten, Euro, vor wie vielen Tagen)
HISTORIE = [(40, "30.00", 120), (45, "30.00", 95), (35, "28.00", 70), (50, "35.00", 42), (40, "30.00", 20)]


def _get_or_create(db: Session, modell, suche: dict, **weitere):
    objekt = db.scalar(select(modell).filter_by(**suche))
    if objekt is None:
        objekt = modell(**suche, **weitere)
        db.add(objekt)
        db.flush()
    return objekt


def anlegen(db: Session) -> None:
    klassen = {b: _get_or_create(db, Instrumentenklasse, {"bezeichnung": b}, oberkategorie=o)
               for b, o in INSTRUMENTENKLASSEN}
    arten = {b: _get_or_create(db, Reparaturart, {"bezeichnung": b}, standard_komplexitaet=k)
             for b, k in REPARATURARTEN}
    for art, klasse, stunden, kosten, notiz in VORGABEWERTE:
        _get_or_create(
            db, ReparaturVorgabewert,
            {"reparaturart_id": arten[art].id, "instrumentenklasse_id": klassen[klasse].id if klasse else None},
            vorgabe_stunden=Decimal(stunden), vorgabe_kosten=Decimal(kosten), notiz=notiz,
        )

    for nummer, name, email, telefon, instrumente in KUNDEN:
        kunde = _get_or_create(db, Kunde, {"kundennummer": nummer}, name=name, email=email, telefon=telefon)
        for klasse, hersteller, typ, baujahr, seriennr in instrumente:
            _get_or_create(
                db, Instrument,
                {"kunde_id": kunde.id, "instrumentenklasse_id": klassen[klasse].id, "typenbezeichnung": typ},
                hersteller=hersteller, baujahr=baujahr, seriennummer=seriennr,
            )

    _historie_anlegen(db, klassen["Violine"], arten["Saitenwechsel"])
    _offene_auftraege_anlegen(db, klassen, arten)
    db.commit()


def _offene_auftraege_anlegen(db: Session, klassen: dict, arten: dict) -> None:
    bearbeiter = db.scalar(select(Mitarbeiter).where(Mitarbeiter.email == DEMO_MITARBEITER_EMAIL))
    status = {s.schluessel: s for s in db.scalars(select(Auftragsstatus))}
    heute = datetime.now(UTC)
    for nummer, kundennr, klasse, art, schluessel, prioritaet, vor_tagen, fertig_in in OFFENE_AUFTRAEGE:
        if db.scalar(select(Auftrag).where(Auftrag.auftragsnummer == nummer)) is not None:
            continue
        instrument = db.scalar(
            select(Instrument).join(Kunde).where(
                Kunde.kundennummer == kundennr, Instrument.instrumentenklasse_id == klassen[klasse].id
            )
        )
        vorgabe = db.scalar(select(ReparaturVorgabewert).where(
            ReparaturVorgabewert.reparaturart_id == arten[art].id,
            (ReparaturVorgabewert.instrumentenklasse_id == klassen[klasse].id)
            | ReparaturVorgabewert.instrumentenklasse_id.is_(None),
        ).order_by(ReparaturVorgabewert.instrumentenklasse_id.is_(None)).limit(1))
        angelegt = heute - timedelta(days=vor_tagen)
        auftrag = Auftrag(
            auftragsnummer=nummer,
            zugriffstoken=secrets.token_hex(6).upper(),
            kunde_id=instrument.kunde_id,
            instrument_id=instrument.id,
            reparaturart_id=arten[art].id,
            zugewiesener_mitarbeiter_id=bearbeiter.id,
            prioritaet=prioritaet,
            komplexitaet=arten[art].standard_komplexitaet,
            status_aktuell_id=status[schluessel].id,
            erstellt_am=angelegt,
            geschaetzte_arbeitsstunden=vorgabe.vorgabe_stunden if vorgabe else None,
            geschaetzte_kosten=vorgabe.vorgabe_kosten if vorgabe else None,
            geschaetztes_fertigstellungsdatum=(heute + timedelta(days=fertig_in)).date(),
            notizen="Demo-Auftrag (offen)",
        )
        db.add(auftrag)
        db.flush()
        verlauf = ["angenommen"] if schluessel == "angenommen" else ["angenommen", schluessel]
        for i, s in enumerate(verlauf):
            db.add(AuftragStatusverlauf(auftrag_id=auftrag.id, status_id=status[s].id,
                                        geaendert_am=angelegt + timedelta(days=i * 2),
                                        geaendert_von_mitarbeiter_id=bearbeiter.id,
                                        kommentar="Auftrag angelegt" if i == 0 else None))
        if status[schluessel].unterbrechungsgrund is not None:  # pausierender Status (2.9)
            db.add(Unterbrechung(auftrag_id=auftrag.id, grund=status[schluessel].unterbrechungsgrund,
                                 von_datum=angelegt + timedelta(days=2)))


def _historie_anlegen(db: Session, violine: Instrumentenklasse, saitenwechsel: Reparaturart) -> None:
    bearbeiter = _get_or_create(
        db, Mitarbeiter, {"email": DEMO_MITARBEITER_EMAIL},
        name="Demo Geigenbauer", rolle="Geigenbauer",
        passwort_hash=passwort_hashen(secrets.token_urlsafe(32)),  # unbekannt → kein Login
    )
    musikschule = db.scalar(select(Kunde).where(Kunde.kundennummer == "DEMO-003"))
    status = {s.schluessel: s for s in db.scalars(select(Auftragsstatus))}
    for nr, (minuten, kosten, tage) in enumerate(HISTORIE, start=1):
        auftragsnummer = f"{DEMO_PRAEFIX}{nr:04d}"
        if db.scalar(select(Auftrag).where(Auftrag.auftragsnummer == auftragsnummer)) is not None:
            continue
        instrument = Instrument(kunde_id=musikschule.id, instrumentenklasse_id=violine.id,
                                hersteller="Musikschul-Leihinstrument", typenbezeichnung=f"Leihgeige {nr}")
        db.add(instrument)
        db.flush()
        angelegt = datetime.now(UTC) - timedelta(days=tage)
        fertig = (angelegt + timedelta(days=3)).date()
        auftrag = Auftrag(
            auftragsnummer=auftragsnummer,
            zugriffstoken=secrets.token_hex(6).upper(),
            kunde_id=musikschule.id,
            instrument_id=instrument.id,
            reparaturart_id=saitenwechsel.id,
            zugewiesener_mitarbeiter_id=bearbeiter.id,
            komplexitaet=1,
            status_aktuell_id=status["abgeholt"].id,
            erstellt_am=angelegt,
            tatsaechliches_fertigstellungsdatum=fertig,
            tatsaechliche_kosten=Decimal(kosten),
            notizen="Demo-Auftrag (Historie)",
        )
        db.add(auftrag)
        db.flush()
        for schluessel, zeitpunkt in [("angenommen", angelegt), ("fertig", angelegt + timedelta(days=3)),
                                      ("abgeholt", angelegt + timedelta(days=5))]:
            db.add(AuftragStatusverlauf(auftrag_id=auftrag.id, status_id=status[schluessel].id,
                                        geaendert_am=zeitpunkt, geaendert_von_mitarbeiter_id=bearbeiter.id))
        db.add(Arbeitszeiterfassung(auftrag_id=auftrag.id, mitarbeiter_id=bearbeiter.id,
                                    dauer_minuten=minuten, erfasst_am=angelegt + timedelta(days=3)))


def entfernen(db: Session) -> None:
    """Entfernt Demo-Kunden mit allen Instrumenten und Aufträgen (auch selbst angelegte
    Testaufträge für Demo-Kunden) sowie den Demo-Mitarbeiter. Stammdaten bleiben."""
    kunden_ids = select(Kunde.id).where(Kunde.kundennummer.startswith(DEMO_PRAEFIX))
    auftrag_ids = select(Auftrag.id).where(Auftrag.kunde_id.in_(kunden_ids))
    for tabelle in (AuftragStatusverlauf, SchaetzungsLog, Arbeitszeiterfassung, Unterbrechung):
        db.execute(delete(tabelle).where(tabelle.auftrag_id.in_(auftrag_ids)))
    db.execute(delete(Auftrag).where(Auftrag.kunde_id.in_(kunden_ids)))
    db.execute(delete(Instrument).where(Instrument.kunde_id.in_(kunden_ids)))
    db.execute(delete(Kunde).where(Kunde.kundennummer.startswith(DEMO_PRAEFIX)))

    bearbeiter = db.scalar(select(Mitarbeiter).where(Mitarbeiter.email == DEMO_MITARBEITER_EMAIL))
    if bearbeiter is not None:
        noch_verwendet = db.scalar(select(Arbeitszeiterfassung.id).where(Arbeitszeiterfassung.mitarbeiter_id == bearbeiter.id).limit(1)) \
            or db.scalar(select(Auftrag.id).where(Auftrag.zugewiesener_mitarbeiter_id == bearbeiter.id).limit(1)) \
            or db.scalar(select(SystemEreignisLog.id).where(SystemEreignisLog.ausgefuehrt_von_mitarbeiter_id == bearbeiter.id).limit(1))
        if noch_verwendet is None:
            db.delete(bearbeiter)
    db.commit()


def anzeigen(db: Session) -> None:
    kunden = db.scalars(select(Kunde).where(Kunde.kundennummer.startswith(DEMO_PRAEFIX)).order_by(Kunde.kundennummer)).all()
    if not kunden:
        print("Keine Demo-Daten vorhanden. Anlegen mit: uv run python -m app.demo_daten anlegen")
        return
    klassen = {k.id: k.bezeichnung for k in db.scalars(select(Instrumentenklasse))}

    print("\nKUNDEN UND INSTRUMENTE")
    for k in kunden:
        print(f"  {k.name} ({k.kundennummer})\n    kunde_id:      {k.id}")
        for i in db.scalars(select(Instrument).where(Instrument.kunde_id == k.id,
                                                     Instrument.hersteller != "Musikschul-Leihinstrument")):
            print(f"    instrument_id: {i.id}   {klassen[i.instrumentenklasse_id]} – {i.hersteller} {i.typenbezeichnung}")

    print("\nREPARATURARTEN")
    for r in db.scalars(select(Reparaturart).order_by(Reparaturart.standard_komplexitaet, Reparaturart.bezeichnung)):
        print(f"  {r.id}   {r.bezeichnung} (Komplexität {r.standard_komplexitaet})")

    print("\nSTATUS")
    for s in db.scalars(select(Auftragsstatus).order_by(Auftragsstatus.reihenfolge)):
        print(f"  {s.id}   {s.bezeichnung}")

    _beispiele(db)


def _beispiele(db: Session) -> None:
    def instrument(kundennr, klasse):
        return db.scalar(select(Instrument).join(Kunde).join(Instrumentenklasse).where(
            Kunde.kundennummer == kundennr, Instrumentenklasse.bezeichnung == klasse,
            Instrument.hersteller != "Musikschul-Leihinstrument"))

    def art(bezeichnung):
        return db.scalar(select(Reparaturart).where(Reparaturart.bezeichnung == bezeichnung))

    faelle = [
        ("Historischer Durchschnitt (5 Demo-Aufträge) → ca. 0,70 Std. / 30,60 €", "DEMO-001", "Violine", "Saitenwechsel"),
        ("Vorgabewert speziell für Violoncello → 1,00 Std. / 45,00 €", "DEMO-003", "Violoncello", "Saitenwechsel"),
        ("Allgemeiner Vorgabewert → 2,50 Std. / 140,00 €", "DEMO-002", "Trompete", "Ventil-Überholung"),
        ("Kein Vorgabewert → keine Schätzung (leer)", "DEMO-002", "Klarinette", "Generalüberholung"),
    ]
    print("\nBEISPIEL-ANFRAGEN FÜR  POST /auftraege  (in /docs bei 'Request body' einfügen)")
    for titel, kundennr, klasse, reparatur in faelle:
        i, r = instrument(kundennr, klasse), art(reparatur)
        if i is None or r is None:
            continue
        print(f"\n  # {titel}")
        print(f'  {{"kunde_id": "{i.kunde_id}", "instrument_id": "{i.id}", "reparaturart_id": "{r.id}"}}')
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Beispieldaten zum Ausprobieren")
    parser.add_argument("aktion", choices=["anlegen", "anzeigen", "entfernen"])
    aktion = parser.parse_args().aktion
    with SessionLocal() as db:
        if aktion == "anlegen":
            anlegen(db)
            print("Beispieldaten angelegt (bereits vorhandene wurden übersprungen).")
            anzeigen(db)
        elif aktion == "anzeigen":
            anzeigen(db)
        else:
            entfernen(db)
            print("Demo-Kunden, ihre Instrumente und Aufträge sowie der Demo-Mitarbeiter wurden entfernt.")
            print("Stammdaten (Instrumentenklassen, Reparaturarten, Vorgabewerte) sind erhalten geblieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
