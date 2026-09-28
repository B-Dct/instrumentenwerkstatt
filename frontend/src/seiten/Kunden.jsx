// Kundenliste (2.1): Liste im Vordergrund, "Neuer Kunde" öffnet das Formular eingebettet (9.10).
// Klick auf eine Zeile führt zur Kundenseite (dort: bearbeiten, Instrumente, archivieren).
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, hatRolle } from '../api.js'
import { AktionsButton, FormularBereich } from '../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../komponenten/fokusFormular.js'
import { useRueckmeldung } from '../komponenten/rueckmeldung.js'
import { useHervorhebung } from '../komponenten/hervorhebung.js'
import { KundeFormular } from './KundeFormular.jsx'

export default function Kunden() {
  const navigate = useNavigate()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [suche, setSuche] = useState('')
  const [archivierte, setArchivierte] = useState(false)
  const [kunden, setKunden] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [neuLaden, setNeuLaden] = useState(0)
  const leitung = hatRolle('werkstattleiter')

  useEffect(() => {
    const timer = setTimeout(() => {
      const filter = { ...(suche.trim() ? { suche: suche.trim() } : {}), ...(archivierte ? { archivierte: true } : {}) }
      api.kunden(filter).then(setKunden).catch((e) => setFehler(e.message))
    }, 250)
    return () => clearTimeout(timer)
  }, [suche, archivierte, neuLaden])

  function angelegt(kunde) {
    formular.gespeichert()
    rueckmeldung(`Kunde ${kunde.name} (${kunde.kundennummer}) angelegt`)
    hervorheben(kunde.id)
    setNeuLaden((n) => n + 1)
  }

  return (
    <>
      <div className="kopf">
        <h1>Kunden</h1>
      </div>

      <div className="aktionsleiste">
        <AktionsButton formular={formular} schluessel="neu" primaer>Neuer Kunde</AktionsButton>
      </div>
      <FormularBereich formular={formular}>
        <KundeFormular key={formular.offen} formular={formular} onGespeichert={angelegt} />
      </FormularBereich>

      <div className="filterleiste">
        <label className="feld feld--inline">
          <span className="unsichtbar">Suche</span>
          <input type="search" placeholder="Suchen: Name, Nr., ext. Nr., E-Mail, Telefon" value={suche}
                 onChange={(e) => setSuche(e.target.value)} />
        </label>
        {leitung && (
          <label className="feld--inline leise">
            <input type="checkbox" checked={archivierte} onChange={(e) => setArchivierte(e.target.checked)} />
            archivierte anzeigen
          </label>
        )}
      </div>

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {kunden === null && !fehler && <p className="leise">Lädt …</p>}
      {kunden?.length === 0 && <p className="leise">{suche ? 'Keine Kunden gefunden.' : 'Noch keine Kunden angelegt.'}</p>}
      {kunden?.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead><tr><th>Kundennr.</th><th>Ext. Nr.</th><th>Name</th><th>E-Mail</th><th>Telefon</th><th></th></tr></thead>
            <tbody>
              {kunden.map((k) => (
                <tr key={k.id} onClick={() => navigate(`/kunden/${k.id}`)}
                    className={[k.id === hervorgehoben && 'zeile--hervorgehoben', k.archiviert_am && 'zeile--archiviert'].filter(Boolean).join(' ') || undefined}>
                  <td>{k.kundennummer}</td>
                  <td>{k.externe_kundennummer ?? '–'}</td>
                  <td><Link to={`/kunden/${k.id}`} onClick={(e) => e.stopPropagation()}>{k.name}</Link></td>
                  <td>{k.email ?? '–'}</td>
                  <td>{k.telefon ?? '–'}</td>
                  <td>{k.archiviert_am && <span className="marke">archiviert</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
