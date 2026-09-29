// Kundenliste (2.1) nach 9.11 (Suche, Filter, Sortierung, Seiten über den Listen-Baustein) und 9.10
// ("Neuer Kunde" öffnet das Formular eingebettet). Klick auf eine Zeile führt zur Kundenseite.
import { Link, useNavigate } from 'react-router'
import { api, datum, hatRolle } from '../api.js'
import { AktionsButton, FormularBereich } from '../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../komponenten/fokusFormular.js'
import { useHervorhebung } from '../komponenten/hervorhebung.js'
import { ListeLeer, Listenkopf, Seitenwahl, SortierKopf } from '../komponenten/Liste.jsx'
import { useListe } from '../komponenten/liste.js'
import { useRueckmeldung } from '../komponenten/rueckmeldung.js'
import { KundeFormular } from './KundeFormular.jsx'

// "archiviert"/"alle" nur für Werkstattleitung und Admin (7.2) – normale Mitarbeiter sehen keinen Filter
const FILTER_LEITUNG = [
  { name: 'status', label: 'Status', standard: 'aktiv', optionen: [
    { wert: 'aktiv', text: 'aktiv' }, { wert: 'archiviert', text: 'archiviert' }, { wert: 'alle', text: 'alle' },
  ] },
]
const KEINE_FILTER = []

export default function Kunden() {
  const navigate = useNavigate()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const liste = useListe({
    laden: api.kunden,
    filter: hatRolle('werkstattleiter') ? FILTER_LEITUNG : KEINE_FILTER,
    sortierung: 'name',
  })
  const { daten, fehler } = liste

  function angelegt(kunde) {
    formular.gespeichert()
    rueckmeldung(`Kunde ${kunde.name} (${kunde.kundennummer}) angelegt`)
    hervorheben(kunde.id)
    liste.neuLaden()
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

      <Listenkopf liste={liste} suchhinweis="Suchen: Name, Nr., ext. Nr., E-Mail, Telefon" />

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {!daten && !fehler && <p className="leise">Lädt …</p>}
      <ListeLeer liste={liste} leerText="Noch keine Kunden angelegt – über „Neuer Kunde“ anlegen." />
      {daten?.eintraege.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr>
                <SortierKopf liste={liste} spalte="kundennummer">Kundennr.</SortierKopf>
                <SortierKopf liste={liste} spalte="externe_kundennummer">Ext. Nr.</SortierKopf>
                <SortierKopf liste={liste} spalte="name">Name</SortierKopf>
                <SortierKopf liste={liste} spalte="email">E-Mail</SortierKopf>
                <SortierKopf liste={liste} spalte="telefon">Telefon</SortierKopf>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {daten.eintraege.map((k) => (
                <tr key={k.id} onClick={() => navigate(`/kunden/${k.id}`)}
                    className={[k.id === hervorgehoben && 'zeile--hervorgehoben', k.archiviert_am && 'zeile--archiviert'].filter(Boolean).join(' ') || undefined}>
                  <td>{k.kundennummer}</td>
                  <td>{k.externe_kundennummer ?? '–'}</td>
                  <td><Link to={`/kunden/${k.id}`} onClick={(e) => e.stopPropagation()}>{k.name}</Link></td>
                  <td>{k.email ?? '–'}</td>
                  <td>{k.telefon ?? '–'}</td>
                  <td>{k.archiviert_am && <span className="marke">archiviert seit {datum(k.archiviert_am)}</span>}</td>
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
