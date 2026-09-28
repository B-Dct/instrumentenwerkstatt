// Gemeinsame Speicher-Logik für eingebettete Formulare: Senden, Fehler je Feld (9.1)
import { useState } from 'react'

export const leerZuNull = (wert) => (typeof wert === 'string' && wert.trim() === '' ? null : wert)

// konfliktFeld: Bei "gibt es bereits" (409) die Meldung direkt an diesem Feld zeigen (9.1)
export function useSpeichern(speichern, onGespeichert, { konfliktFeld } = {}) {
  const [sendet, setSendet] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [felder, setFelder] = useState({})
  async function ausfuehren() {
    setSendet(true); setFehler(null); setFelder({})
    try {
      onGespeichert(await speichern())
    } catch (err) {
      if (err.status === 409 && konfliktFeld) {
        setFelder({ [konfliktFeld]: err.message })
      } else {
        setFehler(err.message); setFelder(err.felder ?? {})
      }
      setSendet(false)
    }
  }
  // Fehler eines Feldes verschwindet, sobald es geändert wird
  const feldGeaendert = (feld) => setFelder((f) => (f[feld] ? { ...f, [feld]: undefined } : f))
  return { sendet, fehler, felder, ausfuehren, feldGeaendert }
}
