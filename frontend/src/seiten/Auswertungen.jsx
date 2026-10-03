// Auswertungen / Jahresstatistik (9.14) – nur Werkstattleitung und Admin (7.2).
// Die Übersicht zeigt den Stand heute, diese Seite die Entwicklung über das gewählte Jahr.
// Grundlage sind die im Jahr abgeschlossenen Aufträge (Fertigstellungsdatum im Jahr).
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { api } from '../api.js'
import { Balkenverteilung, Monatsverlauf } from '../komponenten/Diagramme.jsx'

// Monate, die im laufenden Jahr noch in der Zukunft liegen, zeigen keinen Wert statt einer irreführenden 0
function ohneZukunft(werte, jahr) {
  const heute = new Date()
  return jahr < heute.getFullYear() ? werte : werte.map((w, i) => (i > heute.getMonth() ? null : w))
}

function Kennzahl({ zahl, titel }) {
  return (
    <li><div className="kachel"><span className="kachel__zahl">{zahl}</span><span className="kachel__titel">{titel}</span></div></li>
  )
}

function Menge({ menge, jahr }) {
  const leer = `Im Jahr ${jahr} wurde noch kein Auftrag abgeschlossen.`
  return (
    <section className="abschnitt">
      <h2>Menge</h2>
      <ul className="kacheln" aria-label="Kennzahlen Menge">
        <Kennzahl zahl={menge.abgeschlossen} titel={`Abgeschlossene Aufträge ${jahr}`} />
      </ul>
      <Monatsverlauf titel="Abgeschlossene Aufträge pro Monat" werte={ohneZukunft(menge.pro_monat, jahr)} />
      <div className="spalten">
        <Balkenverteilung titel="Nach Reparaturart" eintraege={menge.nach_reparaturart} leerText={leer} />
        <Balkenverteilung titel="Nach Instrumentenklasse" eintraege={menge.nach_instrumentenklasse} leerText={leer} />
      </div>
    </section>
  )
}

export default function Auswertungen() {
  const [adresse, setAdresse] = useSearchParams()
  const [daten, setDaten] = useState(null)
  const [fehler, setFehler] = useState(null)
  const gewaehlt = adresse.get('jahr')

  useEffect(() => {
    let abgebrochen = false
    api.auswertungen(gewaehlt ? { jahr: gewaehlt } : {})
      .then((d) => { if (!abgebrochen) { setDaten(d); setFehler(null) } })
      .catch((e) => { if (!abgebrochen) setFehler(e.message) })
    return () => { abgebrochen = true }
  }, [gewaehlt])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!daten) return <p className="leise">Lädt …</p>

  // Das laufende Jahr ist der Standard und steht nicht in der Adresse
  const jahrWaehlen = (jahr) => setAdresse(Number(jahr) === daten.jahre[0] ? {} : { jahr }, { replace: true })

  return (
    <>
      <div className="kopf">
        <h1>Auswertungen</h1>
        <label className="feld feld--inline kopf__aktion">
          <span>Jahr</span>
          <select value={daten.jahr} onChange={(e) => jahrWaehlen(e.target.value)}>
            {daten.jahre.map((j) => <option key={j} value={j}>{j}</option>)}
          </select>
        </label>
      </div>
      <p className="leise seitenbeschreibung">
        Gezählt werden die Aufträge, die im Jahr {daten.jahr} abgeschlossen wurden (Fertigstellungsdatum im Jahr,
        nicht der Auftragseingang).
      </p>

      <Menge menge={daten.menge} jahr={daten.jahr} />
    </>
  )
}
