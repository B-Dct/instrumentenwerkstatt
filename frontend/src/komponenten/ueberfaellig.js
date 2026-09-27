// Überfällig (Datenmodell 9.3): geschätztes Fertigstellungsdatum überschritten,
// Auftrag noch nicht abgeschlossen. Kein eigener Status, nur eine zusätzliche Markierung.
export function istUeberfaellig(auftrag) {
  if (!auftrag.geschaetztes_fertigstellungsdatum || auftrag.status.ist_abgeschlossen) return false
  const heute = new Date().toLocaleDateString('sv-SE') // JJJJ-MM-TT in lokaler Zeit
  return auftrag.geschaetztes_fertigstellungsdatum < heute
}
