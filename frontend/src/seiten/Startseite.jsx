// Werkstattleiter-Startseite (9.5) – für Werkstattleitung und Admin die Seite nach dem Login.
// Normale Mitarbeiter landen stattdessen auf der Auftragsliste.
import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router'
import { api, hatRolle } from '../api.js'

// Jede Kachel führt zur Auftragsliste mit genau dem Filter, den die Zahl zählt (9.11)
const KACHELN = [
  { name: 'offen', titel: 'Offene Aufträge', ziel: '/auftraege' },
  { name: 'ueberfaellig', titel: 'Überfällig', ziel: '/auftraege?termin=ueberfaellig', warnung: true },
  { name: 'priorisiert', titel: 'Hohe Priorität', ziel: '/auftraege?prioritaet=hoch' },
  { name: 'pausiert', titel: 'Pausiert', ziel: '/auftraege?pausiert=true' },
]

function Dashboard() {
  const [daten, setDaten] = useState(null)
  const [fehler, setFehler] = useState(null)
  useEffect(() => { api.dashboard().then(setDaten).catch((e) => setFehler(e.message)) }, [])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!daten) return <p className="leise">Lädt …</p>

  return (
    <>
      <div className="kopf">
        <h1>Übersicht</h1>
        <Link to="/neu" className="btn btn--primaer kopf__aktion">Neuer Auftrag</Link>
      </div>

      <ul className="kacheln" aria-label="Kennzahlen">
        {KACHELN.map((k) => {
          const zahl = daten.kennzahlen[k.name]
          return (
            <li key={k.name}>
              <Link to={k.ziel} className={`kachel${k.warnung && zahl > 0 ? ' kachel--warnung' : ''}`}>
                <span className="kachel__zahl">{zahl}</span>
                <span className="kachel__titel">{k.warnung && zahl > 0 && <span aria-hidden="true">⚠ </span>}{k.titel}</span>
              </Link>
            </li>
          )
        })}
      </ul>
    </>
  )
}

export default function Startseite() {
  return hatRolle('werkstattleiter') ? <Dashboard /> : <Navigate to="/auftraege" replace />
}
