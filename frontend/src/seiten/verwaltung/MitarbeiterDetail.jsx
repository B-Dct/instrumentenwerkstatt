// Mitarbeiterseite (2.2, 2.12, 7.4) – nur Admin, nach 9.10: Lesen zuerst, Bearbeiten auf Wunsch.
// Aktionen: Systemrolle ändern · Deaktivieren/Reaktivieren. Schutzregeln (kein Selbst-Deaktivieren,
// kein Selbst-Herabstufen, letzter Admin, offene Aufträge) prüft das Backend; die Oberfläche
// blendet die Aktionen am eigenen Konto gleich aus.
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { angemeldeterNutzer, api, datum, zahl } from '../../api.js'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern } from '../../komponenten/speichern.js'
import { ROLLEN } from './rollen.js'

const ROLLE = 'rolle'

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

  const laden = useCallback(() => api.admin.mitarbeiter(id).then(setMitarbeiter).catch((e) => setFehler(e.message)), [id])
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
      </FormularBereich>
    </>
  )
}
