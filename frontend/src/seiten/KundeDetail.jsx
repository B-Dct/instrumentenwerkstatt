// Kundenseite (2.1, 2.5): Lesen zuerst, Bearbeiten auf Wunsch (9.10).
// Aktionsleiste: Kunde bearbeiten · Instrument hinzufügen · (Leitung) Archivieren/Reaktivieren.
// Klick auf ein Instrument öffnet dessen Formular unter der Aktionsleiste.
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { api, datum, hatRolle } from '../api.js'
import { AktionsButton, FormularBereich } from '../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../komponenten/fokusFormular.js'
import { useHervorhebung } from '../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../komponenten/rueckmeldung.js'
import { InstrumentFormular, KundeFormular } from './KundeFormular.jsx'

const KUNDE_BEARBEITEN = 'kunde'
const INSTRUMENT_NEU = 'instrument-neu'

function instrumentName(i) {
  return [i.hersteller, i.typenbezeichnung].filter(Boolean).join(' ') || '–'
}

export default function KundeDetail() {
  const { id } = useParams()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [kunde, setKunde] = useState(null)
  const [klassen, setKlassen] = useState([])
  const [fehler, setFehler] = useState(null)
  const [aktionsfehler, setAktionsfehler] = useState(null)
  const leitung = hatRolle('werkstattleiter')

  const laden = useCallback(() => api.kunde(id).then(setKunde).catch((e) => setFehler(e.message)), [id])
  useEffect(() => {
    laden()
    api.instrumentenklassen().then(setKlassen).catch(() => {})
  }, [laden])

  async function archivStatus(aufruf, meldung) {
    setAktionsfehler(null)
    if (formular.geaendert) {
      setAktionsfehler('Bitte das offene Formular zuerst speichern oder abbrechen.')
      return
    }
    formular.gespeichert() // offenes (unverändertes) Formular schließen
    try {
      await aufruf()
      rueckmeldung(meldung)
      await laden()
    } catch (err) {
      setAktionsfehler(err.message)
    }
  }

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!kunde) return <p className="leise">Lädt …</p>

  const archiviert = kunde.archiviert_am !== null
  const offenesInstrument = kunde.instrumente.find((i) => i.id === formular.offen)

  function kundeGespeichert(neu) {
    formular.gespeichert()
    setKunde((k) => ({ ...k, ...neu }))
    rueckmeldung('Kunde gespeichert')
    hervorheben(KUNDE_BEARBEITEN)
  }

  async function instrumentGespeichert(instrument, neu) {
    formular.gespeichert()
    rueckmeldung(neu ? 'Instrument hinzugefügt' : 'Instrument gespeichert')
    await laden()
    hervorheben(instrument.id)
  }

  return (
    <>
      <nav className="brotkrumen"><span><Link to="/kunden">Kunden</Link></span><span>{kunde.kundennummer}</span></nav>
      <div className="kopf">
        <h1>{kunde.name}</h1>
        {archiviert && <span className="marke">archiviert seit {datum(kunde.archiviert_am)}</span>}
      </div>

      <dl className={`eckdaten${hervorgehoben === KUNDE_BEARBEITEN ? ' hervorgehoben' : ''}`}>
        <dt>Kundennummer</dt><dd>{kunde.kundennummer}</dd>
        <dt>Externe Kundennummer</dt><dd>{kunde.externe_kundennummer ?? '–'}</dd>
        <dt>E-Mail</dt><dd>{kunde.email ?? '–'}</dd>
        <dt>Telefon</dt><dd>{kunde.telefon ?? '–'}</dd>
        <dt>Kunde seit</dt><dd>{datum(kunde.erstellt_am)}</dd>
      </dl>

      <div className="aktionsleiste">
        {!archiviert && <AktionsButton formular={formular} schluessel={KUNDE_BEARBEITEN}>Kunde bearbeiten</AktionsButton>}
        {!archiviert && <AktionsButton formular={formular} schluessel={INSTRUMENT_NEU}>Instrument hinzufügen</AktionsButton>}
        {leitung && !archiviert && (
          <button type="button" className="btn btn--gefahr aktionsleiste__rechts"
                  onClick={() => archivStatus(() => api.kundeArchivieren(kunde.id),
                    'Kunde archiviert – er bleibt erhalten und kann jederzeit reaktiviert werden')}>
            Kunde archivieren
          </button>
        )}
        {leitung && archiviert && (
          <button type="button" className="btn btn--sekundaer"
                  onClick={() => archivStatus(() => api.kundeReaktivieren(kunde.id), 'Kunde reaktiviert')}>
            Kunde reaktivieren
          </button>
        )}
      </div>
      {aktionsfehler && <p className="meldung meldung--fehler" role="alert">{aktionsfehler}</p>}

      <FormularBereich formular={formular}>
        {formular.offen === KUNDE_BEARBEITEN && (
          <KundeFormular key={KUNDE_BEARBEITEN} formular={formular} kunde={kunde} onGespeichert={kundeGespeichert} />
        )}
        {formular.offen === INSTRUMENT_NEU && (
          <InstrumentFormular key={INSTRUMENT_NEU} formular={formular} kundeId={kunde.id} klassen={klassen}
                              onGespeichert={(i) => instrumentGespeichert(i, true)} />
        )}
        {offenesInstrument && (
          <InstrumentFormular
            key={offenesInstrument.id} formular={formular} kundeId={kunde.id} instrument={offenesInstrument}
            klassen={klassen} onGespeichert={(i) => instrumentGespeichert(i, false)}
          />
        )}
      </FormularBereich>

      <section className="abschnitt">
        <h2>Instrumente</h2>
        {kunde.instrumente.length === 0 && <p className="leise">Noch keine Instrumente erfasst.</p>}
        {kunde.instrumente.length > 0 && (
          <div className="tabelle-rahmen">
            <table className="tabelle tabelle--klickbar">
              <thead><tr><th>Klasse</th><th>Hersteller / Modell</th><th>Baujahr</th><th>Seriennr.</th><th>Notizen</th><th></th></tr></thead>
              <tbody>
                {kunde.instrumente.map((i) => {
                  const instrumentArchiviert = i.archiviert_am !== null
                  const klickbar = !archiviert && !instrumentArchiviert
                  return (
                    <tr key={i.id}
                        className={[i.id === hervorgehoben && 'zeile--hervorgehoben', instrumentArchiviert && 'zeile--archiviert',
                          formular.offen === i.id && 'zeile--ausgewaehlt', !klickbar && 'zeile--nicht-klickbar'].filter(Boolean).join(' ') || undefined}
                        onClick={klickbar ? () => formular.oeffnen(i.id) : undefined}>
                      <td>
                        {klickbar
                          ? <button type="button" className="link-button" aria-expanded={formular.offen === i.id}
                                    onClick={(e) => { e.stopPropagation(); formular.oeffnen(i.id) }}>
                              {i.instrumentenklasse_bezeichnung}
                            </button>
                          : i.instrumentenklasse_bezeichnung}
                        {i.ausfuehrung && <div className="leise klein">{i.ausfuehrung}</div>}
                      </td>
                      <td>{instrumentName(i)}</td>
                      <td>{i.baujahr ?? '–'}</td>
                      <td>{i.seriennummer ?? '–'}</td>
                      <td>{i.notizen ?? ''}</td>
                      <td className="zeilenaktionen">
                        {klickbar && leitung && (
                          <button type="button" className="btn btn--gefahr btn--klein"
                                  onClick={(e) => { e.stopPropagation(); archivStatus(() => api.instrumentArchivieren(i.id),
                                    'Instrument archiviert – es bleibt erhalten und kann reaktiviert werden') }}>
                            Archivieren
                          </button>
                        )}
                        {instrumentArchiviert && <span className="marke">archiviert</span>}
                        {instrumentArchiviert && leitung && !archiviert && (
                          <button type="button" className="btn btn--sekundaer btn--klein"
                                  onClick={(e) => { e.stopPropagation(); archivStatus(() => api.instrumentReaktivieren(i.id), 'Instrument reaktiviert') }}>
                            Reaktivieren
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
