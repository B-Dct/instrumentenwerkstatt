// Mitarbeiterliste (2.2, 7.4) – nur Admin. Liste nach 9.11, Klick auf eine Zeile öffnet die
// Mitarbeiterseite (9.10: Objekt mit Unterobjekten → Leseseite). Neue Konten entstehen per
// Kommandozeile (app.konto_anlegen), deshalb gibt es hier kein "Neu anlegen".
import { useNavigate } from 'react-router'
import { api, datum, zahl } from '../../api.js'
import { ListeLeer, Listenkopf, Seitenwahl, SortierKopf } from '../../komponenten/Liste.jsx'
import { useListe } from '../../komponenten/liste.js'
import { ROLLEN } from './rollen.js'

const FILTER = [
  { name: 'status', label: 'Status', standard: 'aktiv', optionen: [
    { wert: 'aktiv', text: 'aktiv' }, { wert: 'deaktiviert', text: 'deaktiviert' }, { wert: 'alle', text: 'alle' },
  ] },
  { name: 'systemrolle', label: 'Systemrolle', standard: '', optionen: [
    { wert: '', text: 'alle' }, ...Object.entries(ROLLEN).map(([wert, text]) => ({ wert, text })),
  ] },
]

export default function Mitarbeiter() {
  const navigate = useNavigate()
  const liste = useListe({ laden: api.admin.mitarbeiterListe, filter: FILTER, sortierung: 'name' })
  const { daten, fehler } = liste

  return (
    <>
      <div className="kopf"><h1>Mitarbeiter</h1></div>
      <p className="leise seitenbeschreibung">
        Neue Mitarbeiter-Konten werden derzeit per Kommandozeile angelegt (siehe backend/README.md).
      </p>

      <Listenkopf liste={liste} suchhinweis="Suchen: Name, E-Mail, fachliche Rolle" />

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {!daten && !fehler && <p className="leise">Lädt …</p>}
      <ListeLeer liste={liste} leerText="Noch keine Mitarbeiter-Konten." />
      {daten?.eintraege.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr>
                <SortierKopf liste={liste} spalte="name">Name</SortierKopf>
                <SortierKopf liste={liste} spalte="rolle">Fachliche Rolle</SortierKopf>
                <SortierKopf liste={liste} spalte="systemrolle">Systemrolle</SortierKopf>
                <th className="zahl">Wochenstd.</th>
                <th className="zahl">Offene Aufträge</th>
                <SortierKopf liste={liste} spalte="status">Status</SortierKopf>
              </tr>
            </thead>
            <tbody>
              {daten.eintraege.map((m) => (
                <tr key={m.id} className={m.aktiv ? undefined : 'zeile--archiviert'}
                    onClick={() => navigate(`/verwaltung/mitarbeiter/${m.id}`)}>
                  <td>
                    <button type="button" className="link-button"
                            onClick={(e) => { e.stopPropagation(); navigate(`/verwaltung/mitarbeiter/${m.id}`) }}>
                      {m.name}
                    </button>
                    <div className="leise klein">{m.email}</div>
                  </td>
                  <td>{m.rolle ?? '–'}</td>
                  <td>{ROLLEN[m.systemrolle] ?? m.systemrolle}</td>
                  <td className="zahl">
                    {zahl(m.wochenstunden.wochenstunden)}
                    {m.wochenstunden.quelle === 'standard' && <div className="leise klein">Standard</div>}
                  </td>
                  <td className="zahl">{m.offene_auftraege}</td>
                  <td>{m.aktiv ? 'aktiv' : <span className="marke">deaktiviert seit {datum(m.deaktiviert_am)}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Seitenwahl liste={liste} />
    </>
  )
}
