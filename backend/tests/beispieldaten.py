"""Beispieldaten für Tests: eine kleine Werkstatt (werden nach jedem Test zurückgerollt)."""

import secrets
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    Arbeitszeiterfassung,
    Auftrag,
    Auftragsstatus,
    Instrument,
    Instrumentenklasse,
    Kunde,
    Mitarbeiter,
    Reparaturart,
    ReparaturVorgabewert,
)
from app.schaetzung import schaetze_arbeitsstunden, schaetze_kosten


class Werkstatt:
    """Legt Beispieldaten an (werden nach jedem Test zurückgerollt)."""

    def __init__(self, db):
        self.db = db
        self.kunde = Kunde(kundennummer=f"TEST-{secrets.token_hex(4)}", name="Test Kunde")
        self.mitarbeiter = Mitarbeiter(
            name="Test Geigenbauer", email=f"{secrets.token_hex(4)}@test.invalid", passwort_hash="x"
        )
        self.saitenwechsel = Reparaturart(bezeichnung="TEST Saitenwechsel", standard_komplexitaet=1)
        self.kontrabass = Instrumentenklasse(bezeichnung="TEST Kontrabass", oberkategorie="Streich")
        self.violine = Instrumentenklasse(bezeichnung="TEST Violine", oberkategorie="Streich")
        db.add_all([self.kunde, self.mitarbeiter, self.saitenwechsel, self.kontrabass, self.violine])
        db.flush()
        self.status = {s.schluessel: s.id for s in db.scalars(select(Auftragsstatus))}
        self.fertig, self.abgeholt, self.in_bearbeitung = (
            self.status["fertig"], self.status["abgeholt"], self.status["in_bearbeitung"]
        )

    def vorgabe(self, klasse=None, stunden="0.50", kosten="20.00"):
        self.db.add(ReparaturVorgabewert(
            reparaturart_id=self.saitenwechsel.id,
            instrumentenklasse_id=klasse.id if klasse else None,
            vorgabe_stunden=Decimal(stunden),
            vorgabe_kosten=Decimal(kosten),
        ))
        self.db.flush()

    def instrument(self, klasse=None):
        instrument = Instrument(
            kunde_id=self.kunde.id, instrumentenklasse_id=(klasse or self.kontrabass).id
        )
        self.db.add(instrument)
        self.db.flush()
        return instrument

    def auftrag(self, klasse=None, status=None, minuten=(), kosten=None):
        """Ein Auftrag; `minuten` = Zeiteinträge (mehrere Sitzungen möglich)."""
        instrument = self.instrument(klasse)
        auftrag = Auftrag(
            auftragsnummer=f"T-{secrets.token_hex(5)}",
            zugriffstoken=secrets.token_urlsafe(12),
            kunde_id=self.kunde.id,
            instrument_id=instrument.id,
            reparaturart_id=self.saitenwechsel.id,
            komplexitaet=1,
            status_aktuell_id=status or self.fertig,
            tatsaechliche_kosten=None if kosten is None else Decimal(kosten),
        )
        self.db.add(auftrag)
        self.db.flush()
        for m in minuten:
            self.db.add(Arbeitszeiterfassung(
                auftrag_id=auftrag.id, mitarbeiter_id=self.mitarbeiter.id, dauer_minuten=m
            ))
        self.db.flush()

    def stunden(self):
        return schaetze_arbeitsstunden(self.db, self.kontrabass.id, self.saitenwechsel.id)

    def kosten(self):
        return schaetze_kosten(self.db, self.kontrabass.id, self.saitenwechsel.id)
