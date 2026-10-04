"""Standard-Kennzeichen für Ausführungen (Datenmodell 2.6a): Umstellung der bestehenden Richtpreise.

Bisher war die Standardausführung der Eintrag OHNE Namen (ausfuehrung = NULL). Neu trägt bei mehreren
Ausführungen jede einen Namen, und genau eine ist als Standard gekennzeichnet (ist_standard). So lässt
sich ein Instrument mit bewusst eingetragener Standardausführung von einem mit unbekannter Ausführung
unterscheiden.

Die Funktion `anwenden` ist beliebig oft aufrufbar: Ein zweiter Lauf ändert nichts mehr. Sie rät nie –
Kombinationen mit mehreren Ausführungen ohne erkennbaren Standard werden nur gemeldet.
Aufgerufen wird sie von der Migration `vorgabewert_ist_standard`.
"""

from sqlalchemy import Connection, text

# Klassen, deren bisher unbenannter Standardwert laut Quelle (Preisliste Reisser Musik) "Perinet, lackiert" ist
PERINET_LACKIERT = "Perinet, lackiert"
KLASSEN_PERINET = ("Trompete", "Flügelhorn/Kornett")
NOTIZ_HINWEIS = "Standardausführung: Perinet, lackiert. "  # stand bisher in der Notiz, steckt jetzt im Namen
# Von der Werkstatt selbst benannte Standardausführung: (Instrumentenklasse, Reparaturart, Ausführung)
BENANNTE_STANDARDS = (("B-Tuba (3 Ventile)", "Reinigung", "Normal"),)

# Aktive Einträge derselben Kombination aus Reparaturart und Instrumentenklasse (außer v selbst)
_ANDERE = (
    "SELECT 1 FROM reparatur_vorgabewert a WHERE a.archiviert_am IS NULL AND a.id <> v.id "
    "AND a.reparaturart_id = v.reparaturart_id AND a.instrumentenklasse_id = v.instrumentenklasse_id"
)


def anwenden(verbindung: Connection) -> dict:
    """Gibt zurück, wie viel geändert wurde, und unter "offen" die Kombinationen ohne erkennbaren Standard."""
    ergebnis = {"benannt": 0, "standard_gesetzt": 0, "offen": []}

    # 1. Unbenannter Wert neben benannten Ausführungen → bekommt den Namen der Standardausführung
    for klasse in KLASSEN_PERINET:
        ergebnis["benannt"] += verbindung.execute(text(
            "UPDATE reparatur_vorgabewert v SET ausfuehrung = CAST(:name AS varchar), ist_standard = true, "
            "  notiz = NULLIF(REPLACE(v.notiz, CAST(:hinweis AS text), ''), '') "
            "FROM instrumentenklasse k WHERE k.id = v.instrumentenklasse_id AND k.bezeichnung = :klasse "
            "AND v.archiviert_am IS NULL AND v.ausfuehrung IS NULL "
            f"AND EXISTS ({_ANDERE}) "
            f"AND NOT EXISTS ({_ANDERE} AND (a.ist_standard OR a.ausfuehrung = CAST(:name AS varchar)))"
        ), {"klasse": klasse, "name": PERINET_LACKIERT, "hinweis": NOTIZ_HINWEIS}).rowcount

    # 2. Ausdrücklich benannte Standards
    for klasse, reparaturart, ausfuehrung in BENANNTE_STANDARDS:
        ergebnis["standard_gesetzt"] += verbindung.execute(text(
            "UPDATE reparatur_vorgabewert v SET ist_standard = true "
            "FROM instrumentenklasse k, reparaturart r "
            "WHERE k.id = v.instrumentenklasse_id AND r.id = v.reparaturart_id "
            "AND k.bezeichnung = :klasse AND r.bezeichnung = :art AND v.ausfuehrung = :ausfuehrung "
            "AND v.archiviert_am IS NULL AND NOT v.ist_standard "
            f"AND NOT EXISTS ({_ANDERE} AND (a.ist_standard OR a.ausfuehrung IS NULL))"
        ), {"klasse": klasse, "art": reparaturart, "ausfuehrung": ausfuehrung}).rowcount

    # 3. Eine einzelne benannte Ausführung ist zwangsläufig der Standard (nichts zu raten)
    ergebnis["standard_gesetzt"] += verbindung.execute(text(
        "UPDATE reparatur_vorgabewert v SET ist_standard = true "
        "WHERE v.archiviert_am IS NULL AND v.instrumentenklasse_id IS NOT NULL AND v.ausfuehrung IS NOT NULL "
        f"AND NOT v.ist_standard AND NOT EXISTS ({_ANDERE})"
    )).rowcount

    # 4. Was übrig bleibt, wird gemeldet statt geraten: mehrere aktive Werte ohne Standard oder mit unbenanntem Wert
    ergebnis["offen"] = [tuple(zeile) for zeile in verbindung.execute(text(
        "SELECT k.bezeichnung, r.bezeichnung FROM reparatur_vorgabewert v "
        "JOIN instrumentenklasse k ON k.id = v.instrumentenklasse_id JOIN reparaturart r ON r.id = v.reparaturart_id "
        "WHERE v.archiviert_am IS NULL GROUP BY k.bezeichnung, r.bezeichnung "
        "HAVING COUNT(*) > 1 AND (COUNT(*) FILTER (WHERE v.ist_standard) = 0 OR COUNT(*) FILTER (WHERE v.ausfuehrung IS NULL) > 0) "
        "ORDER BY 1, 2"
    ))]
    return ergebnis
