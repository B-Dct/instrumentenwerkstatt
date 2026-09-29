// Auftragsliste nach 9.11 (Suche, Filter, Sortierung, Seiten über den Listen-Baustein).
// Standard (9.4): nur offene Aufträge, Priorität hoch zuerst, dann ältester Eingang zuerst.
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { api, datum, euro, zahl } from '../api.js'
import { ListeLeer, Listenkopf, Seitenwahl, SortierKopf } from '../komponenten/Liste.jsx'
import { useListe } from '../komponenten/liste.js'
import { HohePrioritaet, Status, Ueberfaellig } from '../komponenten/Status.jsx'

const alle = { wert: '', text: 'alle' }

// Optionen für Status, Mitarbeiter und Instrumentenklasse kommen aus den Auswahllisten
function filterAus({ status, mitarbeiter, klassen }) {
  return [
    { name: 'status', label: 'Status', standard: 'offen', optionen: [
      { wert: 'offen', text: 'offen' },
      ...status.filter((s) => !s.ist_abgeschlossen).map((s) => ({ wert: s.schluessel, text: s.bezeichnung })),
      { wert: 'abgeschlossen', text: 'abgeschlossen' },
      ...status.filter((s) => s.ist_abgeschlossen).map((s) => ({ wert: s.schluessel, text: s.bezeichnung })),
      { wert: 'alle', text: 'alle' },
    ] },
    { name: 'mitarbeiter', label: 'Mitarbeiter', standard: '', optionen: [
      alle, { wert: 'keiner', text: 'nicht zugewiesen' }, ...mitarbeiter.map((m) => ({ wert: m.id, text: m.name })),
    ] },
    { name: 'instrumentenklasse_id', label: 'Instrument', standard: '', optionen: [
      alle, ...klassen.map((k) => ({ wert: k.id, text: k.bezeichnung })),
    ] },
    { name: 'prioritaet', label: 'Priorität', standard: '', optionen: [
      alle, { wert: 'hoch', text: 'hoch' }, { wert: 'normal', text: 'normal' },
    ] },
    { name: 'termin', label: 'Termin', standard: 'alle', optionen: [
      { wert: 'alle', text: 'alle' }, { wert: 'ueberfaellig', text: 'überfällig' },
    ] },
  ]
}

export default function AuftragListe() {
  const navigate = useNavigate()
  const [auswahl, setAuswahl] = useState({ status: [], mitarbeiter: [], klassen: [] })
  const [auswahlFehler, setAuswahlFehler] = useState(null)
  const filter = useMemo(() => filterAus(auswahl), [auswahl])
  const liste = useListe({ laden: api.auftraege, filter, sortierung: 'prioritaet', richtung: 'ab' })
  const { daten } = liste
  const fehler = liste.fehler ?? auswahlFehler

  useEffect(() => {
    Promise.all([api.auftragsstatus(), api.mitarbeiter(), api.instrumentenklassen()])
      .then(([status, mitarbeiter, klassen]) => setAuswahl({ status, mitarbeiter, klassen }))
      .catch((e) => setAuswahlFehler(e.message))
  }, [])

  return (
    <>
      <div className="kopf">
        <h1>Aufträge</h1>
        <Link to="/neu" className="btn btn--primaer kopf__aktion">Neuer Auftrag</Link>
      </div>

      <Listenkopf liste={liste} suchhinweis="Suchen: Auftragsnr., Kunde, Instrument" />

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {!daten && !fehler && <p className="leise">Lädt …</p>}
      <ListeLeer liste={liste} leerText="Noch keine Aufträge – über „Neuer Auftrag“ anlegen." />
      {daten?.eintraege.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr>
                <SortierKopf liste={liste} spalte="auftragsnummer">Nr.</SortierKopf>
                <SortierKopf liste={liste} spalte="prioritaet">Priorität</SortierKopf>
                <SortierKopf liste={liste} spalte="status">Status</SortierKopf>
                <SortierKopf liste={liste} spalte="kunde">Kunde</SortierKopf>
                <SortierKopf liste={liste} spalte="instrument">Instrument</SortierKopf>
                <SortierKopf liste={liste} spalte="reparaturart">Reparatur</SortierKopf>
                <SortierKopf liste={liste} spalte="mitarbeiter">Mitarbeiter</SortierKopf>
                <SortierKopf liste={liste} spalte="geschaetzte_arbeitsstunden" zahl>Std.</SortierKopf>
                <SortierKopf liste={liste} spalte="geschaetzte_kosten" zahl>Kosten</SortierKopf>
                <SortierKopf liste={liste} spalte="erstellt_am">Eingang</SortierKopf>
                <SortierKopf liste={liste} spalte="fertigstellung">Fertig bis</SortierKopf>
              </tr>
            </thead>
            <tbody>
              {daten.eintraege.map((a) => (
                <tr key={a.id} className={a.ist_ueberfaellig ? 'zeile--ueberfaellig' : undefined}
                    onClick={() => navigate(`/auftrag/${a.id}`)}>
                  <td><Link to={`/auftrag/${a.id}`} onClick={(e) => e.stopPropagation()}>{a.auftragsnummer}</Link></td>
                  <td>{a.prioritaet === 'hoch' ? <HohePrioritaet /> : <span className="leise">normal</span>}</td>
                  <td>
                    <Status status={a.status} />
                    {a.ist_ueberfaellig && <div><Ueberfaellig /></div>}
                  </td>
                  <td>{a.kunde_name}</td>
                  <td>{a.instrumentenklasse_bezeichnung}</td>
                  <td>{a.reparaturart_bezeichnung}</td>
                  <td>{a.zugewiesener_mitarbeiter_name ?? <span className="leise">nicht zugewiesen</span>}</td>
                  <td className="zahl">{zahl(a.geschaetzte_arbeitsstunden)}</td>
                  <td className="zahl">{euro(a.geschaetzte_kosten)}</td>
                  <td>{datum(a.erstellt_am)}</td>
                  <td>{datum(a.geschaetztes_fertigstellungsdatum)}</td>
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
