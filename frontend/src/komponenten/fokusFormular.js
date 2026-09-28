// Zustand für "Fokussierte Oberflächen" (Datenmodell 9.10):
// - höchstens ein Formular gleichzeitig offen (Schlüssel `offen`, z. B. "neu" oder eine ID)
// - ungespeicherte Änderungen → eingebettete Rückfrage "Änderungen verwerfen?" (kein Popup)
//   beim Wechsel zu einem anderen Formular, beim Abbrechen/Escape und beim Wegnavigieren
// - beim Schließen des Tabs mit ungespeicherten Änderungen: Rückfrage des Browsers
import { useCallback, useEffect, useState } from 'react'
import { useBlocker } from 'react-router'

const SCHLIESSEN = Symbol('schliessen')

export function useFokusFormular() {
  const [offen, setOffen] = useState(null)
  const [geaendert, setGeaendert] = useState(false)
  const [ziel, setZiel] = useState(null) // wartende Aktion, solange die Rückfrage steht

  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    geaendert && currentLocation.pathname !== nextLocation.pathname)

  useEffect(() => {
    if (!geaendert) return undefined
    const warnen = (e) => e.preventDefault()
    window.addEventListener('beforeunload', warnen)
    return () => window.removeEventListener('beforeunload', warnen)
  }, [geaendert])

  const umschalten = useCallback((schluessel) => {
    setOffen(schluessel === SCHLIESSEN ? null : schluessel)
    setGeaendert(false)
    setZiel(null)
  }, [])

  // Formular öffnen; nochmal auf dieselbe Aktion = schließen
  const oeffnen = useCallback((schluessel) => {
    const neu = schluessel === offen ? SCHLIESSEN : schluessel
    if (geaendert) setZiel(neu)
    else umschalten(neu)
  }, [offen, geaendert, umschalten])

  const schliessen = useCallback(() => {
    if (geaendert) setZiel(SCHLIESSEN)
    else umschalten(SCHLIESSEN)
  }, [geaendert, umschalten])

  // Nach erfolgreichem Speichern: ohne Rückfrage schließen
  const gespeichert = useCallback(() => umschalten(SCHLIESSEN), [umschalten])

  const rueckfrageOffen = ziel !== null || blocker.state === 'blocked'

  const verwerfen = useCallback(() => {
    if (blocker.state === 'blocked') {
      setGeaendert(false)
      setOffen(null)
      blocker.proceed()
    } else {
      umschalten(ziel)
    }
  }, [blocker, ziel, umschalten])

  const weiterBearbeiten = useCallback(() => {
    setZiel(null)
    if (blocker.state === 'blocked') blocker.reset()
  }, [blocker])

  return {
    offen, oeffnen, schliessen, gespeichert,
    geaendert, markiereGeaendert: () => setGeaendert(true),
    rueckfrageOffen, verwerfen, weiterBearbeiten,
  }
}
