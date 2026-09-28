// Bausteine für "Fokussierte Oberflächen" (Datenmodell 9.10). Zustand: siehe fokusFormular.js.
import { useEffect, useRef } from 'react'

// Button in der Aktionsleiste: markiert, solange sein Formular offen ist
export function AktionsButton({ formular, schluessel, children, primaer = false }) {
  const aktiv = formular.offen === schluessel
  return (
    <button
      type="button"
      className={`btn ${primaer ? 'btn--primaer' : 'btn--sekundaer'}${aktiv ? ' btn--aktiv' : ''}`}
      aria-expanded={aktiv}
      aria-controls="fokus-formular"
      onClick={() => formular.oeffnen(schluessel)}
    >
      {children}
    </button>
  )
}

// Eingebettete Rückfrage statt Popup
export function Rueckfrage({ formular }) {
  const verwerfenRef = useRef(null)
  useEffect(() => { verwerfenRef.current?.focus() }, [])
  return (
    <div className="rueckfrage" role="alert">
      <p>Es gibt ungespeicherte Änderungen. Änderungen verwerfen?</p>
      <button type="button" className="btn btn--sekundaer btn--klein" ref={verwerfenRef} onClick={formular.verwerfen}>
        Verwerfen
      </button>
      <button type="button" className="btn btn--primaer btn--klein" onClick={formular.weiterBearbeiten}>
        Weiter bearbeiten
      </button>
    </div>
  )
}

// Rahmen für ein eingebettetes Formular: Fokus ins erste Feld, Escape schließt,
// jede Eingabe markiert "geändert", Speichern/Abbrechen unten.
export function FokusFormular({ formular, titel, onSpeichern, sendet, fehler, speichernText = 'Speichern', children, zusatz }) {
  const formRef = useRef(null)

  useEffect(() => {
    formRef.current?.querySelector('input:not([type=hidden]), select, textarea')?.focus()
  }, [])

  return (
    <form
      id="fokus-formular"
      ref={formRef}
      className="fokus-formular"
      aria-label={titel}
      noValidate
      onChange={formular.markiereGeaendert}
      onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); formular.schliessen() } }}
      onSubmit={(e) => { e.preventDefault(); onSpeichern() }}
    >
      <h2>{titel}</h2>
      {children}
      {fehler && <p className="meldung meldung--fehler" role="alert">{fehler}</p>}
      <div className="fokus-formular__aktionen">
        <button className="btn btn--primaer" disabled={sendet}>{sendet ? 'Speichert …' : speichernText}</button>
        <button type="button" className="btn btn--sekundaer" onClick={formular.schliessen}>Abbrechen</button>
        {zusatz}
      </div>
    </form>
  )
}

// Eingabefeld mit Beschriftung und Fehler direkt am Feld (Inline-Validierung, 9.1)
export function Feld({ label, fehler, hinweis, children }) {
  return (
    <label className={`feld${fehler ? ' feld--fehler' : ''}`}>
      <span>{label}</span>
      {children}
      {fehler ? <small className="feld__fehler">{fehler}</small> : hinweis && <small>{hinweis}</small>}
    </label>
  )
}

// Bereich unter der Aktionsleiste: Rückfrage (falls nötig) + das eine offene Formular
export function FormularBereich({ formular, children }) {
  return (
    <>
      {formular.rueckfrageOffen && <Rueckfrage formular={formular} />}
      {formular.offen !== null && children}
    </>
  )
}
