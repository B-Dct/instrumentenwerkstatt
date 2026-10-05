"""Ausführungen als eigene Liste je Instrumentenklasse (Datenmodell 2.4b): Übertragung der Bestandsdaten.

Bisher stand die Ausführung als Text an jedem Richtpreis (samt Standard-Kennzeichen je Reparaturart)
und am Instrument. Neu gibt es je Instrumentenklasse eine Liste von Ausführungen, auf die Richtpreis
und Instrument verweisen. Diese Funktion leitet die Liste aus den Texten ab:

- Gleiche Bezeichnungen einer Klasse werden zusammengeführt; Unterschiede nur in Groß-/Kleinschreibung
  oder Leerzeichen gelten als gleich.
- Der bisherige Standard wird Standard der Klasse. Die bisher unbenannten Richtpreise einer Klasse mit
  Ausführungen gehören zur Standardausführung (so hat die Schätzung sie auch bisher verwendet).
- Eine Ausführung ist aktiv, wenn mindestens ein aktiver Richtpreis sie trägt, sonst archiviert.
- Instrumente werden über den bisherigen Namen verknüpft; ohne Namen bleiben sie "unbekannt".

Es wird nie geraten: Weicht der Standard einer Klasse zwischen Reparaturarten ab oder lässt er sich
nicht bestimmen, bricht die Übertragung mit `NichtEindeutig` ab, ohne etwas zu ändern. Bezeichnungen,
die sich nur durch einen Tippfehler zu unterscheiden scheinen, werden NICHT zusammengeführt, sondern
unter "hinweise" gemeldet.

`uebertragen` ist beliebig oft aufrufbar: Verknüpft wird nur, was noch einen Text, aber keinen Verweis
hat – ein zweiter Lauf ändert nichts. Aufgerufen von der Migration `ausfuehrung_als_liste`, solange
die alten Textspalten noch bestehen.
"""

from collections import Counter, defaultdict

from sqlalchemy import Connection, text


class NichtEindeutig(Exception):
    """Die Daten lassen keine eindeutige Übertragung zu (Liste der Gründe in .probleme)."""

    def __init__(self, probleme: list[str]):
        super().__init__("Ausführungen nicht eindeutig übertragbar:\n- " + "\n- ".join(probleme))
        self.probleme = probleme


def schluessel(bezeichnung: str) -> str:
    """Groß-/Kleinschreibung und überzählige Leerzeichen spielen keine Rolle."""
    return " ".join(bezeichnung.split()).casefold()


def _abstand(a: str, b: str) -> int:
    """Anzahl der Einfügungen, Löschungen und Ersetzungen zwischen zwei Texten (Levenshtein)."""
    vorige = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        aktuelle = [i]
        for j, y in enumerate(b, 1):
            aktuelle.append(min(vorige[j] + 1, aktuelle[j - 1] + 1, vorige[j - 1] + (x != y)))
        vorige = aktuelle
    return vorige[-1]


def aehnlich(a: str, b: str) -> bool:
    """Sieht nach Tippfehler aus: gleich bis auf Satzzeichen oder höchstens zwei abweichende Zeichen."""
    a, b = schluessel(a), schluessel(b)
    nur_zeichen = ["".join(z for z in t if z.isalnum()) for t in (a, b)]
    return a != b and (nur_zeichen[0] == nur_zeichen[1] or (min(len(a), len(b)) > 4 and _abstand(a, b) <= 2))


def uebertragen(verbindung: Connection) -> dict:
    """Gibt zurück, was angelegt und verknüpft wurde, und unter "hinweise" mögliche Tippfehler."""
    je_klasse: dict = defaultdict(lambda: defaultdict(
        lambda: {"schreibweisen": Counter(), "aktiv": False, "standard": False, "archiviert_am": None}))
    klassenname = dict(verbindung.execute(text("SELECT id, bezeichnung FROM instrumentenklasse")).all())

    for klasse, name, standard, archiviert_am in verbindung.execute(text(
        "SELECT instrumentenklasse_id, ausfuehrung, ist_standard, archiviert_am FROM reparatur_vorgabewert "
        "WHERE ausfuehrung IS NOT NULL AND ausfuehrung_id IS NULL AND instrumentenklasse_id IS NOT NULL"
    )):
        eintrag = je_klasse[klasse][schluessel(name)]
        eintrag["schreibweisen"][" ".join(name.split())] += 1
        if archiviert_am is None:
            eintrag["aktiv"] = True
            eintrag["standard"] = eintrag["standard"] or standard
        else:
            eintrag["archiviert_am"] = max(filter(None, [eintrag["archiviert_am"], archiviert_am]))
    for klasse, name in verbindung.execute(text(
        "SELECT instrumentenklasse_id, ausfuehrung FROM instrument WHERE ausfuehrung IS NOT NULL AND ausfuehrung_id IS NULL"
    )):
        je_klasse[klasse][schluessel(name)]["schreibweisen"][" ".join(name.split())] += 1

    # Was es für die Klasse schon gibt (zweiter Lauf, oder inzwischen von Hand angelegt)
    vorhanden: dict = defaultdict(dict)
    for id_, klasse, bezeichnung, standard, archiviert_am in verbindung.execute(text(
        "SELECT id, instrumentenklasse_id, bezeichnung, ist_standard, archiviert_am FROM ausfuehrung ORDER BY archiviert_am NULLS LAST"
    )):
        vorhanden[klasse][schluessel(bezeichnung)] = {"id": id_, "standard": standard and archiviert_am is None,
                                                      "aktiv": archiviert_am is None}

    # Erst alles prüfen, dann ändern
    probleme, hinweise, standard_je_klasse = [], [], {}
    for klasse, namen in je_klasse.items():
        bezeichnung = klassenname[klasse]
        anzeige = {k: e["schreibweisen"].most_common(1)[0][0] for k, e in namen.items()}
        aktive = {k for k, e in namen.items() if e["aktiv"]} | {k for k, e in vorhanden[klasse].items() if e["aktiv"]}
        standards = {k for k, e in namen.items() if e["standard"]} | {k for k, e in vorhanden[klasse].items() if e["standard"]}
        if len(standards) > 1:
            probleme.append(f"{bezeichnung}: Der Standard weicht zwischen den Reparaturarten ab "
                            f"({', '.join(sorted(anzeige.get(k, k) for k in standards))})")
        elif len(standards) == 1:
            standard_je_klasse[klasse] = next(iter(standards))
        elif len(aktive) == 1:
            standard_je_klasse[klasse] = next(iter(aktive))  # die einzige aktive Ausführung ist zwangsläufig der Standard
        elif aktive:
            probleme.append(f"{bezeichnung}: mehrere Ausführungen, aber keine ist als Standard gekennzeichnet "
                            f"({', '.join(sorted(anzeige.get(k, k) for k in aktive))})")
        alle = sorted(anzeige.values())
        hinweise += [f"{bezeichnung}: „{a}“ und „{b}“ unterscheiden sich kaum – Tippfehler?"
                     for i, a in enumerate(alle) for b in alle[i + 1:] if aehnlich(a, b)]
    # Ein unbenannter Wert neben dem benannten Standard derselben Reparaturart ließe sich nicht zuordnen
    for klasse, standard in standard_je_klasse.items():
        doppelt = verbindung.execute(text(
            "SELECT r.bezeichnung FROM reparatur_vorgabewert u JOIN reparaturart r ON r.id = u.reparaturart_id "
            "WHERE u.instrumentenklasse_id = :k AND u.archiviert_am IS NULL AND u.ausfuehrung IS NULL AND u.ausfuehrung_id IS NULL "
            "AND EXISTS (SELECT 1 FROM reparatur_vorgabewert b WHERE b.instrumentenklasse_id = :k AND b.archiviert_am IS NULL "
            "  AND b.reparaturart_id = u.reparaturart_id AND b.ausfuehrung_id IS NULL "
            "  AND lower(regexp_replace(btrim(b.ausfuehrung), '\\s+', ' ', 'g')) = lower(CAST(:s AS varchar)))"
        ), {"k": klasse, "s": standard}).scalars().all()
        probleme += [f"{klassenname[klasse]} / {art}: ein Wert ohne Ausführung steht neben dem benannten Standard" for art in doppelt]
    if probleme:
        raise NichtEindeutig(probleme)

    ergebnis = {"ausfuehrungen": 0, "richtpreise": 0, "instrumente": 0, "dem_standard_zugeordnet": 0, "hinweise": hinweise}
    for klasse, namen in je_klasse.items():
        for name, eintrag in namen.items():
            ausfuehrung_id = vorhanden[klasse].get(name, {}).get("id")
            if ausfuehrung_id is None:
                ausfuehrung_id = verbindung.execute(text(
                    "INSERT INTO ausfuehrung (instrumentenklasse_id, bezeichnung, ist_standard, archiviert_am) "
                    "VALUES (:k, :b, :s, :a) RETURNING id"
                ), {"k": klasse, "b": eintrag["schreibweisen"].most_common(1)[0][0],
                    "s": eintrag["aktiv"] and standard_je_klasse.get(klasse) == name,
                    # Nur noch an archivierten Richtpreisen oder an Instrumenten: archiviert, die Verweise bleiben
                    "a": None if eintrag["aktiv"] else eintrag["archiviert_am"] or verbindung.execute(text("SELECT clock_timestamp()")).scalar_one(),
                    }).scalar_one()
                ergebnis["ausfuehrungen"] += 1
            for tabelle, zaehler in (("reparatur_vorgabewert", "richtpreise"), ("instrument", "instrumente")):
                ergebnis[zaehler] += verbindung.execute(text(
                    f"UPDATE {tabelle} SET ausfuehrung_id = :a WHERE instrumentenklasse_id = :k AND ausfuehrung_id IS NULL "
                    "AND lower(regexp_replace(btrim(ausfuehrung), '\\s+', ' ', 'g')) = lower(CAST(:n AS varchar))"
                ), {"a": ausfuehrung_id, "k": klasse, "n": name}).rowcount

    # Unbenannte Richtpreise einer Klasse MIT Ausführungen gehören zur Standardausführung (2.4b)
    ergebnis["dem_standard_zugeordnet"] = verbindung.execute(text(
        "UPDATE reparatur_vorgabewert v SET ausfuehrung_id = a.id FROM ausfuehrung a "
        "WHERE a.instrumentenklasse_id = v.instrumentenklasse_id AND a.ist_standard AND a.archiviert_am IS NULL "
        "AND v.ausfuehrung_id IS NULL AND v.ausfuehrung IS NULL"
    )).rowcount
    return ergebnis
