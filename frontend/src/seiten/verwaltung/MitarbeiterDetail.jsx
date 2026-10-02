// Mitarbeiterseite (2.2, 2.12, 7.4) – nur Admin, nach 9.10: Lesen zuerst, Bearbeiten auf Wunsch.
// Aktionen: Wochenstunden ändern · Systemrolle ändern · Deaktivieren/Reaktivieren.
// Darunter der zugeklappte Wochenstunden-Verlauf (2.12). Schutzregeln (kein Selbst-Deaktivieren,
// kein Selbst-Herabstufen, letzter Admin, offene Aufträge) prüft das Backend; die Oberfläche
// blendet die Aktionen am eigenen Konto gleich aus.
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { angemeldeterNutzer, api, datum, zahl, zeit } from '../../api.js'
import Aufklappbereich from '../../komponenten/Aufklappbereich.jsx'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern } from '../../komponenten/speichern.js'
import { ROLLEN } from './rollen.js'

const ROLLE = 'rolle'
const WOCHENSTUNDEN = 'wochenstunden'

const isoDatum = (d) => d.toLocaleDateString('sv-SE') // JJJJ-MM-TT in lokaler Zeit
function naechsterTag(iso) {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + 1)
  return isoDatum(d)
}

// Ein neuer Wert muss nach dem Beginn des bisher offenen Eintrags liegen (2.12)
function fruehesterBeginn(offenerEintrag) {
  const heute = isoDatum(new Date())
  if (!offenerEintrag) return { vorschlag: heute, minimum: null }
  const minimum = naechsterTag(offenerEintrag.gueltig_ab)
  return { vorschlag: minimum > heute ? minimum : heute, minimum }
}

function WochenstundenFormular({ formular, mitarbeiter, offenerEintrag, onGespeichert }) {
  const { vorschlag, minimum } = fruehesterBeginn(offenerEintrag)
  const [werte, setWerte] = useState({ wochenstunden: '', gueltig_ab: vorschlag })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(
    () => api.admin.wochenstundenFestlegen(mitarbeiter.id, {
      wochenstunden: werte.wochenstunden === '' ? null : Number(werte.wochenstunden),
      gueltig_ab: werte.gueltig_ab || null,
    }),
    onGespeichert,
    { konfliktFeld: 'gueltig_ab' },
  )
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }
  return (
    <FokusFormular formular={formular} titel="Wochenstunden ändern" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}>
      <div className="spalten spalten--eng">
        <Feld label="Wochenstunden" fehler={felder.wochenstunden} hinweis="Über 0, höchstens 80, bis zu 2 Nachkommastellen">
          <input type="number" min="0.01" max="80" step="0.25" value={werte.wochenstunden}
                 onChange={setze('wochenstunden')} required />
        </Feld>
        <Feld label="Gültig ab" fehler={felder.gueltig_ab}
              hinweis={minimum ? `Frühestens ${datum(minimum)} (Tag nach Beginn des aktuellen Werts)` : 'Auch rückwirkend möglich'}>
          <input type="date" value={werte.gueltig_ab} min={minimum ?? undefined} onChange={setze('gueltig_ab')} required />
        </Feld>
      </div>
      <p className="leise">
        Der bisherige Wert endet automatisch am Vortag und bleibt im Verlauf erhalten. Neue Terminschätzungen
        rechnen sofort mit dem neuen Wert; bereits berechnete Termine offener Aufträge werden nicht automatisch
        angepasst (Abschnitt 4.0a). Bei Bedarf lassen sie sich per Kommandozeile neu berechnen
        (<code>termine_nachrechnen --alle</code>, siehe backend/README.md).
      </p>
    </FokusFormular>
  )
}

function Verlauf({ verlauf }) {
  const eintraege = verlauf?.eintraege ?? []
  const heute = isoDatum(new Date())
  const zusammenfassung = !verlauf ? 'Lädt …'
    : eintraege.length === 0 ? 'Noch keine Wochenstunden hinterlegt – es gilt der Standard von 40 Std.'
    : `${eintraege.length} ${eintraege.length === 1 ? 'Eintrag' : 'Einträge'}, zuletzt ${zahl(eintraege[0].wochenstunden)} Std. ab ${datum(eintraege[0].gueltig_ab)}`
  return (
    <Aufklappbereich titel="Verlauf der Wochenstunden" zusammenfassung={zusammenfassung}>
      {eintraege.length === 0 ? <p className="leise">{zusammenfassung}</p> : (
        <div className="tabelle-rahmen">
          <table className="tabelle">
            <thead><tr><th>Zeitraum</th><th className="zahl">Wochenstd.</th><th>Geändert von</th><th>Geändert am</th></tr></thead>
            <tbody>
              {eintraege.map((e) => {
                const geplant = e.gueltig_ab > heute
                const aktuell = !geplant && (e.gueltig_bis === null || e.gueltig_bis >= heute)
                return (
                  <tr key={e.id}>
                    <td>
                      {datum(e.gueltig_ab)} – {e.gueltig_bis ? datum(e.gueltig_bis) : 'offen'}
                      {aktuell && <span className="marke marke--aktuell">aktuell</span>}
                      {geplant && <span className="marke">geplant</span>}
                    </td>
                    <td className="zahl">{zahl(e.wochenstunden)}</td>
                    <td>{e.geaendert_von_name ?? '–'}</td>
                    <td>{zeit(e.geaendert_am)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Aufklappbereich>
  )
}

function RolleFormular({ formular, mitarbeiter, onGespeichert }) {
  const [rolle, setRolle] = useState(mitarbeiter.systemrolle)
  const { sendet, fehler, felder, ausfuehren } = useSpeichern(
    () => api.admin.systemrolleAendern(mitarbeiter.id, rolle), onGespeichert,
  )
  return (
    <FokusFormular formular={formular} titel="Systemrolle ändern" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}>
      <Feld label="Systemrolle" fehler={felder.systemrolle}
            hinweis="Bestimmt die Berechtigungen (7.2). Die Änderung wirkt sofort, auch bei bestehender Anmeldung.">
        <select value={rolle} onChange={(e) => setRolle(e.target.value)}>
          {Object.entries(ROLLEN).map(([wert, text]) => <option key={wert} value={wert}>{text}</option>)}
        </select>
      </Feld>
    </FokusFormular>
  )
}

export default function MitarbeiterDetail() {
  const { id } = useParams()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [mitarbeiter, setMitarbeiter] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [aktionsfehler, setAktionsfehler] = useState(null)

  const [verlauf, setVerlauf] = useState(null)

  const laden = useCallback(() => Promise.all([api.admin.mitarbeiter(id), api.admin.wochenstunden(id)])
    .then(([m, v]) => { setMitarbeiter(m); setVerlauf(v) })
    .catch((e) => setFehler(e.message)), [id])
  useEffect(() => { laden() }, [laden])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!mitarbeiter) return <p className="leise">Lädt …</p>

  const selbst = mitarbeiter.id === angemeldeterNutzer()?.id
  const m = mitarbeiter

  async function statusWechseln(aktivieren) {
    setAktionsfehler(null)
    if (formular.geaendert) {
      setAktionsfehler('Bitte das offene Formular zuerst speichern oder abbrechen.')
      return
    }
    formular.gespeichert()
    try {
      const neu = await (aktivieren ? api.admin.mitarbeiterAktivieren(m.id) : api.admin.mitarbeiterDeaktivieren(m.id))
      setMitarbeiter(neu)
      rueckmeldung(aktivieren
        ? `${m.name} reaktiviert – die Anmeldung ist wieder möglich`
        : `${m.name} deaktiviert – die Anmeldung ist gesperrt, das Konto bleibt mit allen Daten erhalten`)
      hervorheben('status')
    } catch (err) {
      setAktionsfehler(err.message)
    }
  }

  async function wochenstundenGespeichert(neuerVerlauf) {
    formular.gespeichert()
    setVerlauf(neuerVerlauf)
    const neu = neuerVerlauf.eintraege[0]
    rueckmeldung(`Wochenstunden von ${m.name}: ${zahl(neu.wochenstunden)} Std. ab ${datum(neu.gueltig_ab)}`)
    setMitarbeiter(await api.admin.mitarbeiter(m.id))
    hervorheben('status')
  }

  function rolleGespeichert(neu) {
    formular.gespeichert()
    setMitarbeiter(neu)
    rueckmeldung(`Systemrolle von ${neu.name}: ${ROLLEN[neu.systemrolle]}`)
    hervorheben('status')
  }

  return (
    <>
      <nav className="brotkrumen"><span><Link to="/verwaltung/mitarbeiter">Mitarbeiter</Link></span><span>{m.name}</span></nav>
      <div className="kopf">
        <h1>{m.name}</h1>
        {!m.aktiv && <span className="marke">deaktiviert seit {datum(m.deaktiviert_am)}</span>}
      </div>

      <dl className={`eckdaten${hervorgehoben === 'status' ? ' hervorgehoben' : ''}`}>
        <dt>E-Mail (Anmeldung)</dt><dd>{m.email}</dd>
        <dt>Fachliche Rolle</dt><dd>{m.rolle ?? '–'}</dd>
        <dt>Systemrolle</dt><dd>{ROLLEN[m.systemrolle] ?? m.systemrolle}</dd>
        <dt>Wochenstunden</dt>
        <dd>
          {zahl(m.wochenstunden.wochenstunden)} Std.{' '}
          <span className="leise">
            {m.wochenstunden.quelle === 'standard'
              ? '(Standard, nichts hinterlegt)'
              : `(hinterlegt, gültig ab ${datum(m.wochenstunden.gueltig_ab)})`}
          </span>
        </dd>
        <dt>Offene Aufträge</dt><dd>{m.offene_auftraege}</dd>
        <dt>Konto seit</dt><dd>{datum(m.erstellt_am)}</dd>
      </dl>

      <div className="aktionsleiste">
        {m.aktiv && <AktionsButton formular={formular} schluessel={WOCHENSTUNDEN}>Wochenstunden ändern</AktionsButton>}
        {!selbst && m.aktiv && <AktionsButton formular={formular} schluessel={ROLLE}>Systemrolle ändern</AktionsButton>}
        {!selbst && m.aktiv && (
          <button type="button" className="btn btn--gefahr aktionsleiste__rechts" onClick={() => statusWechseln(false)}>
            Deaktivieren
          </button>
        )}
        {!m.aktiv && (
          <button type="button" className="btn btn--sekundaer" onClick={() => statusWechseln(true)}>Reaktivieren</button>
        )}
      </div>
      {selbst && (
        <p className="leise">
          Das ist dein eigenes Konto: Es lässt sich hier nicht deaktivieren und die Admin-Rolle nicht entziehen
          (Schutz gegen Aussperren).
        </p>
      )}
      {!selbst && m.aktiv && m.offene_auftraege > 0 && (
        <p className="leise">
          Hinweis: Zum Deaktivieren müssen zuerst die {m.offene_auftraege} offenen Aufträge neu zugewiesen werden.
        </p>
      )}
      {aktionsfehler && <p className="meldung meldung--fehler" role="alert">{aktionsfehler}</p>}

      <FormularBereich formular={formular}>
        {formular.offen === ROLLE && <RolleFormular key={ROLLE} formular={formular} mitarbeiter={m} onGespeichert={rolleGespeichert} />}
        {formular.offen === WOCHENSTUNDEN && (
          <WochenstundenFormular key={WOCHENSTUNDEN} formular={formular} mitarbeiter={m}
                                 offenerEintrag={verlauf?.eintraege.find((e) => e.gueltig_bis === null)}
                                 onGespeichert={wochenstundenGespeichert} />
        )}
      </FormularBereich>

      <Verlauf verlauf={verlauf} />
    </>
  )
}
