import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api, datum, euro, stunden } from '../api.js'

export function StatusMarke({ status }) {
  return <span className="status" style={{ background: status.farbe }}>{status.bezeichnung}</span>
}

export default function AuftragListe() {
  const [auftraege, setAuftraege] = useState(null)
  const [nurOffene, setNurOffene] = useState(true)
  const [fehler, setFehler] = useState(null)

  useEffect(() => {
    api.auftraege(nurOffene ? { nur_offene: true } : {}).then(setAuftraege).catch((e) => setFehler(e.message))
  }, [nurOffene])

  return (
    <>
      <h1>Aufträge</h1>
      <label>
        <input type="checkbox" checked={nurOffene} onChange={(e) => { setAuftraege(null); setNurOffene(e.target.checked) }} /> nur offene
      </label>
      <p><Link to="/neu">+ Neuer Auftrag</Link></p>
      {fehler && <p className="fehler">{fehler}</p>}
      {auftraege === null && !fehler && <p>Lädt …</p>}
      {auftraege?.length === 0 && <p>Keine Aufträge vorhanden.</p>}
      {auftraege?.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Nr.</th><th>Priorität</th><th>Status</th><th>Kunde</th><th>Instrument</th>
              <th>Reparatur</th><th>Mitarbeiter</th><th>Geschätzt</th><th>Eingang</th>
            </tr>
          </thead>
          <tbody>
            {auftraege.map((a) => (
              <tr key={a.id}>
                <td><Link to={`/auftrag/${a.id}`}>{a.auftragsnummer}</Link></td>
                <td>{a.prioritaet === 'hoch' ? '⚑ hoch' : 'normal'}</td>
                <td><StatusMarke status={a.status} /></td>
                <td>{a.kunde_name}</td>
                <td>{a.instrumentenklasse_bezeichnung}</td>
                <td>{a.reparaturart_bezeichnung}</td>
                <td>{a.zugewiesener_mitarbeiter_name ?? '–'}</td>
                <td>{stunden(a.geschaetzte_arbeitsstunden)} / {euro(a.geschaetzte_kosten)}</td>
                <td>{datum(a.erstellt_am)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
