import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api, datum, euro, zahl } from '../api.js'
import { HohePrioritaet, Status, Ueberfaellig } from '../komponenten/Status.jsx'
import { istUeberfaellig } from '../komponenten/ueberfaellig.js'

export default function AuftragListe() {
  const [auftraege, setAuftraege] = useState(null)
  const [nurOffene, setNurOffene] = useState(true)
  const [fehler, setFehler] = useState(null)

  useEffect(() => {
    api.auftraege(nurOffene ? { nur_offene: true } : {}).then(setAuftraege).catch((e) => setFehler(e.message))
  }, [nurOffene])

  return (
    <>
      <div className="kopf">
        <h1>Aufträge</h1>
        <label className="feld--inline leise">
          <input type="checkbox" checked={nurOffene} onChange={(e) => { setAuftraege(null); setNurOffene(e.target.checked) }} />
          nur offene
        </label>
        <Link to="/neu" className="btn btn--primaer kopf__aktion">Neuer Auftrag</Link>
      </div>

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {auftraege === null && !fehler && <p className="leise">Lädt …</p>}
      {auftraege?.length === 0 && <p className="leise">{nurOffene ? 'Keine offenen Aufträge.' : 'Keine Aufträge vorhanden.'}</p>}
      {auftraege?.length > 0 && (
        <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead>
            <tr>
              <th>Nr.</th><th>Status</th><th>Kunde</th><th>Instrument</th><th>Reparatur</th>
              <th>Mitarbeiter</th><th className="zahl">Std.</th><th className="zahl">Kosten</th><th>Eingang</th>
            </tr>
          </thead>
          <tbody>
            {auftraege.map((a) => {
              const ueberfaellig = istUeberfaellig(a)
              return (
                <tr key={a.id} className={ueberfaellig ? 'zeile--ueberfaellig' : undefined}>
                  <td>
                    <Link to={`/auftrag/${a.id}`}>{a.auftragsnummer}</Link>
                    {a.prioritaet === 'hoch' && <div><HohePrioritaet /></div>}
                  </td>
                  <td>
                    <Status status={a.status} />
                    {ueberfaellig && <div><Ueberfaellig /></div>}
                  </td>
                  <td>{a.kunde_name}</td>
                  <td>{a.instrumentenklasse_bezeichnung}</td>
                  <td>{a.reparaturart_bezeichnung}</td>
                  <td>{a.zugewiesener_mitarbeiter_name ?? <span className="leise">nicht zugewiesen</span>}</td>
                  <td className="zahl">{zahl(a.geschaetzte_arbeitsstunden)}</td>
                  <td className="zahl">{euro(a.geschaetzte_kosten)}</td>
                  <td>{datum(a.erstellt_am)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
      )}
    </>
  )
}
