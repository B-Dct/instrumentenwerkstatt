// Nicht blockierende Erfolgsbestätigung am Bildschirmrand (Datenmodell 9.1), verschwindet von selbst.
import { useCallback, useRef, useState } from 'react'
import { RueckmeldungKontext as Kontext } from './rueckmeldung.js'

const ANZEIGEDAUER_MS = 4000

export function RueckmeldungBereich({ children }) {
  const [meldung, setMeldung] = useState(null)
  const timer = useRef(null)

  const zeigen = useCallback((text) => {
    clearTimeout(timer.current)
    setMeldung({ text, id: Date.now() })
    timer.current = setTimeout(() => setMeldung(null), ANZEIGEDAUER_MS)
  }, [])

  return (
    <Kontext.Provider value={zeigen}>
      {children}
      <div className="rueckmeldung" role="status" aria-live="polite">
        {meldung && <p key={meldung.id} className="rueckmeldung__text"><span aria-hidden="true">✓</span> {meldung.text}</p>}
      </div>
    </Kontext.Provider>
  )
}
