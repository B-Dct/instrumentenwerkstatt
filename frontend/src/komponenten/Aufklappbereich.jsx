// Zugeklappter Lese-Bereich (Datenmodell 9.10, Regel 6): einzeilige Zusammenfassung,
// Klick klappt den Inhalt auf. Echter Button mit aria-expanded (Regel 7).
import { useId, useState } from 'react'

export default function Aufklappbereich({ titel, zusammenfassung, children, offen: anfangsOffen = false }) {
  const [offen, setOffen] = useState(anfangsOffen)
  const inhaltId = useId()
  return (
    <section className="abschnitt aufklappbereich">
      <h2>
        <button type="button" className="aufklappbereich__knopf" aria-expanded={offen} aria-controls={inhaltId}
                onClick={() => setOffen((o) => !o)}>
          <span aria-hidden="true" className="aufklappbereich__zeichen">{offen ? '▾' : '▸'}</span>
          {titel}
        </button>
      </h2>
      {!offen && zusammenfassung && <p className="leise aufklappbereich__zusammenfassung">{zusammenfassung}</p>}
      <div id={inhaltId} hidden={!offen}>{offen && children}</div>
    </section>
  )
}
