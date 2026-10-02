// Werkstattleiter-Startseite (9.5) – für Werkstattleitung und Admin die Seite nach dem Login.
// Normale Mitarbeiter landen stattdessen auf der Auftragsliste.
import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router'
import { api, datum, hatRolle, zahl } from '../api.js'
import { HohePrioritaet, Status, Ueberfaellig } from '../komponenten/Status.jsx'

// Jede Kachel führt zur Auftragsliste mit genau dem Filter, den die Zahl zählt (9.11)
const KACHELN = [
  { name: 'offen', titel: 'Offene Aufträge', ziel: '/auftraege' },
  { name: 'ueberfaellig', titel: 'Überfällig', ziel: '/auftraege?termin=ueberfaellig', warnung: true },
  { name: 'priorisiert', titel: 'Hohe Priorität', ziel: '/auftraege?prioritaet=hoch' },
  { name: 'pausiert', titel: 'Pausiert', ziel: '/auftraege?pausiert=true' },
]

function NaechsteFaellige({ auftraege }) {
  return (
    <section className="abschnitt">
      <h2>Nächste fällige Aufträge</h2>
      {auftraege.length === 0 ? <p className="leise">Kein offener Auftrag mit Termin.</p> : (
        <ul className="faellig">
          {auftraege.map((a) => (
            <li key={a.id}>
              <Link to={`/auftrag/${a.id}`} className="faellig__eintrag">
                <span className="faellig__termin">
                  {datum(a.geschaetztes_fertigstellungsdatum)}
                  {a.ist_ueberfaellig && <Ueberfaellig />}
                </span>
                <span className="faellig__auftrag">
                  <span><strong>{a.auftragsnummer}</strong> · {a.kunde_name}</span>
                  <span className="leise">{a.instrumentenklasse_bezeichnung}, {a.reparaturart_bezeichnung} · {a.zugewiesener_mitarbeiter_name ?? 'nicht zugewiesen'}</span>
                </span>
                <span className="faellig__status">
                  <Status status={a.status} />
                  {a.prioritaet === 'hoch' && <HohePrioritaet />}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p><Link to="/auftraege?sortierung=fertigstellung&richtung=auf">Alle offenen Aufträge nach Termin</Link></p>
    </section>
  )
}

// Stufen wie in 9.9: unter 80 % frei, 80–100 % fast voll, darüber überbucht – immer Farbe UND Text (9.3)
function stufe(prozent) {
  if (prozent > 100) return { name: 'rot', text: 'überbucht' }
  if (prozent >= 80) return { name: 'gelb', text: 'fast voll' }
  return { name: 'gruen', text: 'frei' }
}

function AuslastungListe({ zeilen, wocheVon }) {
  return (
    <section className="abschnitt">
      <h2>Auslastung</h2>
      <p className="leise seitenbeschreibung">
        Woche ab {datum(wocheVon)}: Abwesenheiten dieser Woche plus geschätzte Stunden aller zugewiesenen offenen Aufträge,
        gemessen an den Wochenstunden.
      </p>
      {zeilen.length === 0 ? <p className="leise">Es gibt noch keine aktiven Mitarbeiter.</p> : (
        <ul className="auslastung">
          {zeilen.map((z) => {
            const s = stufe(z.auslastung_prozent)
            return (
              <li key={z.mitarbeiter_id} className={`auslastung__zeile auslastung__zeile--${s.name}`}>
                <div className="auslastung__kopf">
                  <Link to={`/auftraege?mitarbeiter=${z.mitarbeiter_id}`}>{z.name}</Link>
                  <span><strong>{z.auslastung_prozent} %</strong> · {s.text}</span>
                </div>
                <div className="auslastung__balken" role="img"
                     aria-label={`${z.name}: ${z.auslastung_prozent} Prozent ausgelastet, ${s.text}`}>
                  <span style={{ width: `${Math.min(100, z.auslastung_prozent)}%` }} />
                </div>
                <small className="leise">
                  {zahl(z.auftragsstunden)} Std. in {z.offene_auftraege} {z.offene_auftraege === 1 ? 'offenem Auftrag' : 'offenen Aufträgen'}
                  {z.abwesenheitsstunden > 0 && ` + ${zahl(z.abwesenheitsstunden)} Std. abwesend`}
                  {' '}von {zahl(z.wochenstunden)} Wochenstunden ·{' '}
                  {z.freie_stunden >= 0 ? `${zahl(z.freie_stunden)} Std. frei` : `${zahl(-z.freie_stunden)} Std. zu viel`}
                </small>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

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

      <div className="spalten">
        <NaechsteFaellige auftraege={daten.naechste_faellige} />
        <AuslastungListe zeilen={daten.auslastung} wocheVon={daten.woche_von} />
      </div>
    </>
  )
}

export default function Startseite() {
  return hatRolle('werkstattleiter') ? <Dashboard /> : <Navigate to="/auftraege" replace />
}
