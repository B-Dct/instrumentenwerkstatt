"""Datenformate der API (was hinein- und herausgeht)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, PlainSerializer, StringConstraints

from app.models import Abwesenheitstyp, Prioritaet, Systemrolle

# Dezimalwerte als JSON-Zahl ausgeben (statt als Text "12.50")
Stunden = Annotated[
    Decimal, Field(ge=0, max_digits=6, decimal_places=2), PlainSerializer(float, return_type=float)
]
Euro = Annotated[
    Decimal, Field(ge=0, max_digits=10, decimal_places=2), PlainSerializer(float, return_type=float)
]


# --- Reparatur-Vorgabewerte (Datenmodell 2.6a) ------------------------------

# Leere Eingabe = Standardausführung
Ausfuehrung = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=100), AfterValidator(lambda w: w or None)
]


class AusfuehrungAuswahl(BaseModel):
    """Eine wählbare Ausführung im Auftragsformular samt ihrer Vorgabewerte."""

    ausfuehrung: str | None  # None = Standardausführung
    vorgabe_stunden: Stunden
    vorgabe_kosten: Euro

class VorgabewertNeu(BaseModel):
    reparaturart_id: uuid.UUID
    instrumentenklasse_id: uuid.UUID | None = None  # None = gilt allgemein für die Reparaturart
    ausfuehrung: Ausfuehrung = None  # None = Standardausführung; nur zusammen mit einer Instrumentenklasse
    vorgabe_stunden: Stunden
    vorgabe_kosten: Euro
    notiz: str | None = None


class VorgabewertAenderung(BaseModel):
    """Nur mitgeschickte Felder werden geändert."""

    reparaturart_id: uuid.UUID | None = None
    instrumentenklasse_id: uuid.UUID | None = None  # explizit null = auf "allgemein" setzen
    ausfuehrung: Ausfuehrung = None  # explizit null/leer = Standardausführung
    vorgabe_stunden: Stunden | None = None
    vorgabe_kosten: Euro | None = None
    notiz: str | None = None


class Vorgabewert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reparaturart_id: uuid.UUID
    reparaturart_bezeichnung: str
    instrumentenklasse_id: uuid.UUID | None
    instrumentenklasse_bezeichnung: str | None
    ausfuehrung: str | None  # None = Standardausführung
    vorgabe_stunden: Stunden
    vorgabe_kosten: Euro
    notiz: str | None
    archiviert_am: datetime | None  # NULL = aktiv
    geaendert_von_mitarbeiter_id: uuid.UUID | None
    geaendert_am: datetime


# --- Aufträge (Datenmodell 2.7, 2.8, 2.10, 4.2) -----------------------------

class AuftragNeu(BaseModel):
    kunde_id: uuid.UUID
    instrument_id: uuid.UUID  # muss dem Kunden gehören
    reparaturart_id: uuid.UUID
    # Nur wenn es für Reparaturart + Instrumentenklasse mehrere Vorgabewerte gibt (2.6a); None = Standard
    ausfuehrung: Ausfuehrung = None
    zugewiesener_mitarbeiter_id: uuid.UUID | None = None
    prioritaet: Prioritaet = Prioritaet.normal
    # Weggelassen = Standard-Komplexität der Reparaturart
    komplexitaet: int | None = Field(None, ge=1, le=5)
    notizen: str | None = None


class StatusKurz(BaseModel):
    id: uuid.UUID
    schluessel: str
    bezeichnung: str
    farbe: str
    symbol: str
    ist_abgeschlossen: bool


class AuftragKurz(BaseModel):
    """Eintrag in der Auftragsliste."""

    id: uuid.UUID
    auftragsnummer: str
    kunde_id: uuid.UUID
    kunde_name: str
    instrument_id: uuid.UUID
    instrumentenklasse_bezeichnung: str
    reparaturart_id: uuid.UUID
    reparaturart_bezeichnung: str
    zugewiesener_mitarbeiter_id: uuid.UUID | None
    zugewiesener_mitarbeiter_name: str | None
    prioritaet: Prioritaet
    komplexitaet: int
    status: StatusKurz
    erstellt_am: datetime
    geschaetzte_arbeitsstunden: Stunden | None
    geschaetzte_kosten: Euro | None
    geschaetztes_fertigstellungsdatum: date | None
    # Termin überschritten und noch nicht abgeschlossen (9.3) – Markierung, kein Status
    ist_ueberfaellig: bool


class StatusverlaufEintrag(BaseModel):
    status: StatusKurz
    geaendert_am: datetime
    geaendert_von_mitarbeiter_id: uuid.UUID | None
    # Name direkt mitgeliefert – bleibt sichtbar, auch wenn der Mitarbeiter deaktiviert ist
    geaendert_von_name: str | None
    kommentar: str | None


class SchaetzungsLogEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    berechnet_am: datetime
    methode: str
    geschaetzte_stunden: Stunden | None
    geschaetzte_kosten: Euro | None
    geschaetztes_datum: date | None
    eingabefaktoren: dict | None
    korrigiert_von_mitarbeiter_id: uuid.UUID | None
    korrigiert_von_name: str | None = None  # auch für deaktivierte Mitarbeiter
    grund: str | None


class UnterbrechungEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    grund: str
    von_datum: datetime
    bis_datum: datetime | None  # None = noch offen


class AuftragDetail(AuftragKurz):
    zugriffstoken: str  # für den Abgabebeleg (Kunden-Dashboard, Abschnitt 6)
    geschaetzte_bandbreite_von: date | None
    geschaetzte_bandbreite_bis: date | None
    tatsaechliches_fertigstellungsdatum: date | None
    tatsaechliche_kosten: Euro | None
    notizen: str | None
    statusverlauf: list[StatusverlaufEintrag]  # älteste zuerst
    schaetzungen: list[SchaetzungsLogEintrag]  # älteste zuerst
    unterbrechungen: list[UnterbrechungEintrag]  # älteste zuerst


class AuftragAenderung(BaseModel):
    """Zuweisung/Priorität ändern (Werkstattleitung/Admin). Nur mitgeschickte Felder zählen."""

    zugewiesener_mitarbeiter_id: uuid.UUID | None = None  # explizit null = Zuweisung aufheben
    prioritaet: Prioritaet | None = None


class Statuswechsel(BaseModel):
    status_id: uuid.UUID
    kommentar: str | None = None
    # Beides Pflicht, wenn der Zielstatus den Abschluss erfasst (z. B. "Fertig", Datenmodell 9.8):
    # die aufgewendete Arbeitszeit und der tatsächlich abgerechnete Betrag
    arbeitszeit_minuten: int | None = Field(None, gt=0)
    abgerechneter_betrag: Euro | None = None
    # Nur bei pausierenden Status (z. B. "Wartet auf Ersatzteil"); leer = Standardgrund des Status
    unterbrechungsgrund: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class SchaetzungKorrektur(BaseModel):
    geschaetzte_arbeitsstunden: Stunden | None = None
    geschaetzte_kosten: Euro | None = None
    grund: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Begründung der Korrektur (Pflicht)"
    )


class TerminKorrektur(BaseModel):
    """Manuelle Korrektur des Fertigstellungstermins (4.2) – nur Werkstattleitung/Admin."""

    geschaetztes_fertigstellungsdatum: date
    grund: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Begründung der Korrektur (Pflicht)"
    )


# --- Auswahllisten (nur lesen) -----------------------------------------------

class InstrumentKurz(BaseModel):
    id: uuid.UUID
    kunde_id: uuid.UUID
    instrumentenklasse_id: uuid.UUID
    instrumentenklasse_bezeichnung: str
    hersteller: str | None
    typenbezeichnung: str | None
    baujahr: int | None
    seriennummer: str | None
    notizen: str | None
    archiviert_am: datetime | None


class ReparaturartKurz(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bezeichnung: str
    standard_komplexitaet: int


class StatusEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schluessel: str
    bezeichnung: str
    reihenfolge: int
    farbe: str
    symbol: str
    erfordert_abschlussdaten: bool
    unterbrechungsgrund: str | None
    ist_abgeschlossen: bool


class MitarbeiterKurz(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rolle: str | None


# --- Kunden und Instrumente (2.1, 2.5) ----------------------------------------

Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text150 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]


def _leer_zu_none(wert):
    """Leere oder nur aus Leerzeichen bestehende Eingabe = kein Wert (NULL, nicht leerer Text)."""
    return None if isinstance(wert, str) and not wert.strip() else wert


# Kundennummer aus dem Buchhaltungssystem: optional, getrimmt, leer = kein Wert
ExterneKundennummer = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None,
    BeforeValidator(_leer_zu_none),
]


class KundeNeu(BaseModel):
    name: Text200
    externe_kundennummer: ExterneKundennummer = None
    email: EmailStr | None = None
    telefon: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None


class KundeAenderung(BaseModel):
    """Nur mitgeschickte Felder werden geändert; null leert optionale Felder."""

    name: Text200 | None = None
    externe_kundennummer: ExterneKundennummer = None
    email: EmailStr | None = None
    telefon: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None


class KundeEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kundennummer: str
    externe_kundennummer: str | None
    name: str
    email: str | None
    telefon: str | None
    erstellt_am: datetime
    archiviert_am: datetime | None


class InstrumentNeu(BaseModel):
    kunde_id: uuid.UUID
    instrumentenklasse_id: uuid.UUID
    hersteller: Text150 | None = None
    typenbezeichnung: Text150 | None = None
    baujahr: int | None = Field(None, ge=1500, le=2100)
    seriennummer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    notizen: str | None = None


class InstrumentAenderung(BaseModel):
    """Nur mitgeschickte Felder werden geändert. Der Eigentümer (Kunde) ist nicht änderbar."""

    instrumentenklasse_id: uuid.UUID | None = None
    hersteller: Text150 | None = None
    typenbezeichnung: Text150 | None = None
    baujahr: int | None = Field(None, ge=1500, le=2100)
    seriennummer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    notizen: str | None = None


class KundeDetail(KundeEintrag):
    instrumente: list["InstrumentKurz"]


# --- Stammdaten: Instrumentenklassen (2.4), Reparaturarten (2.6) --------------

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text150Pflicht = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class InstrumentenklasseNeu(BaseModel):
    bezeichnung: Text100
    oberkategorie: Text100


class InstrumentenklasseAenderung(BaseModel):
    bezeichnung: Text100 | None = None
    oberkategorie: Text100 | None = None


class InstrumentenklasseEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bezeichnung: str
    oberkategorie: str
    archiviert_am: datetime | None


class ReparaturartNeu(BaseModel):
    bezeichnung: Text150Pflicht
    standard_komplexitaet: int = Field(ge=1, le=5)


class ReparaturartAenderung(BaseModel):
    bezeichnung: Text150Pflicht | None = None
    standard_komplexitaet: int | None = Field(None, ge=1, le=5)


class ReparaturartEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bezeichnung: str
    standard_komplexitaet: int
    archiviert_am: datetime | None


# --- Mitarbeiter-Verwaltung (2.2, 2.12, 7.4) – nur Admin ------------------------

class AktuelleWochenstunden(BaseModel):
    wochenstunden: Stunden
    # "hinterlegt" = Eintrag in mitarbeiter_arbeitszeit; "standard" = Fallback (nichts hinterlegt)
    quelle: Literal["hinterlegt", "standard"]
    gueltig_ab: date | None  # None beim Standard


class MitarbeiterVerwaltung(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    rolle: str | None  # fachliche Rolle
    systemrolle: Systemrolle
    aktiv: bool
    erstellt_am: datetime
    deaktiviert_am: datetime | None
    wochenstunden: AktuelleWochenstunden
    offene_auftraege: int  # zugewiesene, noch nicht abgeschlossene Aufträge


class SystemrolleAenderung(BaseModel):
    systemrolle: Systemrolle


class WochenstundenNeu(BaseModel):
    wochenstunden: Annotated[Decimal, Field(gt=0, le=80, max_digits=5, decimal_places=2)]
    gueltig_ab: date


class WochenstundenEintrag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wochenstunden: Stunden
    gueltig_ab: date
    gueltig_bis: date | None  # None = aktuell gültig
    geaendert_von_mitarbeiter_id: uuid.UUID | None
    geaendert_von_name: str | None = None  # auch für deaktivierte Mitarbeiter
    geaendert_am: datetime


class WochenstundenVerlauf(BaseModel):
    aktuell: AktuelleWochenstunden
    eintraege: list[WochenstundenEintrag]  # neueste zuerst


# --- Abwesenheiten (Datenmodell 2.3) -------------------------------------------

VerfuegbareStunden = Annotated[Decimal, Field(gt=0, le=80, max_digits=5, decimal_places=2)]
# Leere Notiz = keine Notiz
Notiz = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(lambda w: w or None)
]


class AbwesenheitNeu(BaseModel):
    mitarbeiter_id: uuid.UUID | None = None  # None = ganze Werkstatt (Feiertag, Betriebsschließung)
    typ: Abwesenheitstyp
    von_datum: date
    bis_datum: date
    # Verfügbare Wochenstunden im Zeitraum (None = ganztägig abwesend); bei jedem persönlichen Typ möglich
    reduzierte_stunden: VerfuegbareStunden | None = None
    notiz: Notiz = None


class AbwesenheitAenderung(BaseModel):
    """Nur mitgeschickte Felder werden geändert."""

    mitarbeiter_id: uuid.UUID | None = None
    typ: Abwesenheitstyp | None = None
    von_datum: date | None = None
    bis_datum: date | None = None
    reduzierte_stunden: VerfuegbareStunden | None = None
    notiz: Notiz = None


class AbwesenheitEintrag(BaseModel):
    id: uuid.UUID
    mitarbeiter_id: uuid.UUID | None
    mitarbeiter_name: str | None  # None = ganze Werkstatt
    typ: Abwesenheitstyp
    von_datum: date
    bis_datum: date
    reduzierte_stunden: Stunden | None
    notiz: str | None
    storniert_am: datetime | None  # None = gilt


class RasterZeile(BaseModel):
    mitarbeiter_id: uuid.UUID
    name: str
    normalstunden: list[Stunden]  # je Tag des Ausschnitts: Wochenstunden / 5, am Wochenende 0


class AbwesenheitsRaster(BaseModel):
    """Ausschnitt für das Abwesenheits-Raster (9.13)."""

    von: date
    bis: date
    tage: list[date]
    zeilen: list[RasterZeile]  # aktive Mitarbeiter; die Zeile "Ganze Werkstatt" ergänzt die Oberfläche
    abwesenheiten: list[AbwesenheitEintrag]  # alle, die den Ausschnitt berühren (auch werkstattweite)


# --- Werkstatt-Einstellungen (Datenmodell 7.5) ---------------------------------

class EinstellungEintrag(BaseModel):
    schluessel: str
    bezeichnung: str
    beschreibung: str
    art: Literal["auswahl", "zahl"]
    einheit: str | None  # nur bei Zahlen, z. B. "€/Std."
    optionen: list[str]  # bei art = auswahl: erlaubte Werte (kein Freitext)
    wert: str | None  # None = noch nicht festgelegt
    geaendert_von_name: str | None
    geaendert_am: datetime | None


class EinstellungWert(BaseModel):
    wert: str


# --- Feiertage erzeugen (Datenmodell 9.13.1) -----------------------------------

class FeiertageNeu(BaseModel):
    jahr: int


class FeiertagTag(BaseModel):
    datum: date
    name: str


class FeiertageErgebnis(BaseModel):
    jahr: int
    bundesland: str
    angelegt: list[FeiertagTag]
    uebersprungen: list[FeiertagTag]  # schon vorhanden oder früher erzeugt (nichts wird überschrieben)


class FeiertageJahr(BaseModel):
    jahr: int
    bundesland: str  # Bundesland beim ersten Erzeugen dieses Jahres
    erzeugt_am: datetime
    anzahl: int  # insgesamt automatisch angelegte Feiertage


class FeiertageStand(BaseModel):
    bundesland: str | None  # aktuelle Einstellung
    jahr_von: int  # erlaubter Bereich für "Feiertage für Jahr X erzeugen"
    jahr_bis: int
    jahre: list[FeiertageJahr]


# --- Werkstattleiter-Startseite (Datenmodell 9.5) ------------------------------

class DashboardKennzahlen(BaseModel):
    """Jede Zahl entspricht der Trefferzahl der Auftragsliste mit dem passenden Filter."""

    offen: int
    ueberfaellig: int  # Termin vorbei, nicht abgeschlossen
    priorisiert: int  # offen mit hoher Priorität
    pausiert: int  # offen mit laufender Unterbrechung (2.9)


class Auslastung(BaseModel):
    """Auslastung eines Mitarbeiters in der laufenden Woche (Formel aus 8.2)."""

    mitarbeiter_id: uuid.UUID
    name: str
    wochenstunden: float
    abwesenheitsstunden: float  # in dieser Woche (ganztägig oder reduzierte Stunden, auch werkstattweit)
    auftragsstunden: float  # geschätzte Stunden aller zugewiesenen offenen Aufträge
    offene_auftraege: int
    freie_stunden: float  # Wochenstunden − Abwesenheit − Aufträge; negativ = überbucht
    auslastung_prozent: int  # (Abwesenheit + Aufträge) / Wochenstunden


class HeuteAbwesend(BaseModel):
    """Eine heute geltende Abwesenheit (9.13)."""

    mitarbeiter_id: uuid.UUID | None  # None = ganze Werkstatt (Feiertag, Betriebsschließung)
    name: str | None
    typ: Abwesenheitstyp
    bis_datum: date
    verfuegbare_tagesstunden: float | None  # None = ganztägig abwesend
    notiz: str | None


class Dashboard(BaseModel):
    kennzahlen: DashboardKennzahlen
    naechste_faellige: list[AuftragKurz]  # offene Aufträge mit dem nächstgelegenen Termin
    woche_von: date  # Montag der Woche, für die die Auslastung gilt
    auslastung: list[Auslastung]  # je aktivem Mitarbeiter
    heute_abwesend: list[HeuteAbwesend]  # werkstattweite Einträge zuerst


# --- Auswertungen / Jahresstatistik (Datenmodell 9.14) --------------------------

class Verteilung(BaseModel):
    bezeichnung: str
    anzahl: int
    sonstige: bool = False  # Sammelzeile für alles außerhalb der Top 5


class AuswertungMenge(BaseModel):
    """9.14.1 – im Jahr abgeschlossene Aufträge."""

    abgeschlossen: int
    pro_monat: list[int]  # 12 Werte, Januar bis Dezember
    nach_reparaturart: list[Verteilung]  # Top 5 + ggf. "Sonstige"
    nach_instrumentenklasse: list[Verteilung]


class AuswertungZeit(BaseModel):
    """9.14.2 – None bedeutet jeweils: keine Grundlage im gewählten Jahr."""

    bearbeitungsdauer_tage: float | None  # Ø Kalendertage von Eingang bis Fertigstellung
    bearbeitungsdauer_pro_monat: list[float | None]  # 12 Werte nach Monat der Fertigstellung
    arbeitszeit_stunden: float | None  # Ø erfasste Arbeitszeit je Auftrag mit Zeiterfassung
    auftraege_mit_zeiterfassung: int
    # Pünktlich = nicht später fertig als die ERSTE automatische Terminschätzung (nicht Korrekturen)
    puenktlich: int
    auftraege_mit_terminprognose: int
    puenktlichkeit_prozent: int | None


class AuswertungGeld(BaseModel):
    """9.14.3 – Grundlage: im Jahr abgeschlossene Aufträge mit eingetragenen tatsächlichen Kosten."""

    umsatz: float
    auftragswert: float | None  # Ø je Auftrag mit eingetragenen Kosten; None = keine Grundlage
    auftraege_mit_kosten: int
    umsatz_pro_monat: list[float]  # 12 Werte nach Monat der Fertigstellung


class Abweichung(BaseModel):
    """Erste automatische Schätzung gegen den Ist-Wert, in Prozent der Schätzung. None = keine Grundlage."""

    abweichung_prozent: int | None  # Ø ohne Vorzeichen: wie weit daneben
    tendenz_prozent: int | None  # Ø mit Vorzeichen: positiv = tatsächlich mehr als geschätzt
    auftraege: int  # Aufträge mit Schätzung UND Ist-Wert


class AuswertungSchaetzgenauigkeit(BaseModel):
    """9.14.4 – misst das automatische Modell, nicht spätere manuelle Korrekturen."""

    stunden: Abweichung
    kosten: Abweichung


class Auswertung(BaseModel):
    jahr: int
    jahre: list[int]  # wählbare Jahre, neuestes zuerst
    menge: AuswertungMenge
    zeit: AuswertungZeit
    geld: AuswertungGeld
    schaetzgenauigkeit: AuswertungSchaetzgenauigkeit
