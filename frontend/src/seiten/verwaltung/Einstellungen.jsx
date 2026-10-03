// Werkstatt-Einstellungen (7.5) – nur Admin, nach 9.10: Werte im Lesezustand,
// "… ändern" öffnet das Formular eingebettet. Werte kommen aus einer Auswahl (kein Freitext)
// oder sind eine Zahl mit Einheit (z. B. Stundensatz).
// Dazu die Admin-Aktion "Feiertage für Jahr X erzeugen" (9.13.1), die am Bundesland hängt.
import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api, datum, zeit } from '../../api.js'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern, vorabPruefen } from '../../komponenten/speichern.js'

// Zahlen mit Komma und Einheit anzeigen (gespeichert wird z. B. "47.5")
const anzeige = (e) => (e.art === 'zahl' ? `${Number(e.wert).toLocaleString('de-DE')} ${e.einheit ?? ''}`.trim() : e.wert)

function EinstellungFormular({ formular, einstellung, onGespeichert }) {
  const [wert, setWert] = useState(einstellung.wert ?? '')
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    vorabPruefen({ wert: !wert && (einstellung.art === 'zahl' ? 'Pflichtfeld' : 'Bitte auswählen') })
    return api.admin.einstellungSetzen(einstellung.schluessel, String(wert))
  }, onGespeichert)
  return (
    <FokusFormular formular={formular} titel={`${einstellung.bezeichnung} ${einstellung.wert ? 'ändern' : 'festlegen'}`}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}>
      <Feld label={einstellung.einheit ? `${einstellung.bezeichnung} in ${einstellung.einheit}` : einstellung.bezeichnung}
            fehler={felder.wert} hinweis={einstellung.beschreibung}>
        {einstellung.art === 'zahl' ? (
          <input type="number" min="0.01" step="0.01" value={wert} onChange={(e) => { feldGeaendert('wert'); setWert(e.target.value) }} required />
        ) : (
          <select value={wert} onChange={(e) => { feldGeaendert('wert'); setWert(e.target.value) }} required>
            <option value="">Bitte wählen</option>
            {einstellung.optionen.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
      </Feld>
    </FokusFormular>
  )
}

const FEIERTAGE = 'feiertage'

function FeiertageFormular({ formular, stand, onGespeichert }) {
  const jahre = Array.from({ length: stand.jahr_bis - stand.jahr_von + 1 }, (_, i) => stand.jahr_von + i)
  const erzeugt = new Set(stand.jahre.map((j) => j.jahr))
  // Vorschlag: das nächste Jahr ab heute, für das noch nichts erzeugt wurde
  const heute = new Date().getFullYear()
  const [jahr, setJahr] = useState(String(jahre.find((j) => j >= heute && !erzeugt.has(j)) ?? heute))
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(
    () => api.admin.feiertageErzeugen(Number(jahr)), onGespeichert,
  )
  return (
    <FokusFormular formular={formular} titel="Feiertage erzeugen" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText="Feiertage erzeugen">
      <Feld label="Jahr" fehler={felder.jahr}
            hinweis={`Gesetzliche Feiertage für ${stand.bundesland}. Vorhandene, geänderte oder stornierte Feiertage bleiben unverändert – es wird nur Fehlendes ergänzt.`}>
        <select value={jahr} onChange={(e) => { feldGeaendert('jahr'); setJahr(e.target.value) }}>
          {jahre.map((j) => <option key={j} value={j}>{j}{erzeugt.has(j) ? ' (bereits erzeugt)' : ''}</option>)}
        </select>
      </Feld>
    </FokusFormular>
  )
}

export default function Einstellungen() {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [einstellungen, setEinstellungen] = useState(null)
  const [feiertage, setFeiertage] = useState(null)
  const [letztesErgebnis, setLetztesErgebnis] = useState(null)
  const [fehler, setFehler] = useState(null)

  const laden = useCallback(() => Promise.all([api.admin.einstellungen(), api.admin.feiertage()])
    .then(([e, f]) => { setEinstellungen(e); setFeiertage(f) })
    .catch((e) => setFehler(e.message)), [])
  useEffect(() => { laden() }, [laden])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!einstellungen || !feiertage) return <p className="leise">Lädt …</p>

  function gespeichert(neu) {
    formular.gespeichert()
    setEinstellungen((alle) => alle.map((e) => (e.schluessel === neu.schluessel ? neu : e)))
    rueckmeldung(`${neu.bezeichnung}: ${anzeige(neu)}`)
    hervorheben(neu.schluessel)
    // Beim Festlegen des Bundeslands entstehen die Feiertage für dieses und das nächste Jahr automatisch
    api.admin.feiertage().then(setFeiertage).catch(() => {})
  }

  function feiertageErzeugt(ergebnis) {
    formular.gespeichert()
    setLetztesErgebnis(ergebnis)
    const n = ergebnis.angelegt.length
    rueckmeldung(n > 0
      ? `Feiertage ${ergebnis.jahr}: ${n} angelegt${ergebnis.uebersprungen.length ? `, ${ergebnis.uebersprungen.length} schon vorhanden` : ''}`
      : `Feiertage ${ergebnis.jahr}: nichts zu ergänzen, alle ${ergebnis.uebersprungen.length} schon vorhanden`)
    hervorheben(FEIERTAGE)
    api.admin.feiertage().then(setFeiertage).catch(() => {})
  }

  const offen = einstellungen.find((e) => e.schluessel === formular.offen)

  return (
    <>
      <div className="kopf"><h1>Einstellungen</h1></div>
      <p className="leise seitenbeschreibung">Einstellungen, die für die ganze Werkstatt gelten.</p>

      <dl className="eckdaten">
        {einstellungen.map((e) => (
          <Fragment key={e.schluessel}>
            <dt>{e.bezeichnung}</dt>
            <dd className={hervorgehoben === e.schluessel ? 'hervorgehoben' : undefined}>
              {e.wert === null ? <span className="leise">noch nicht festgelegt</span> : anzeige(e)}
              {e.geaendert_am && (
                <span className="leise"> (geändert am {zeit(e.geaendert_am)}{e.geaendert_von_name ? ` von ${e.geaendert_von_name}` : ''})</span>
              )}
            </dd>
          </Fragment>
        ))}
      </dl>

      <div className="aktionsleiste">
        {einstellungen.map((e) => (
          <AktionsButton key={e.schluessel} formular={formular} schluessel={e.schluessel}>
            {e.bezeichnung} {e.wert ? 'ändern' : 'festlegen'}
          </AktionsButton>
        ))}
      </div>

      {/* Rückfrage und Formular erscheinen jeweils bei der Aktion, zu der sie gehören */}
      {formular.offen !== FEIERTAGE && (
        <FormularBereich formular={formular}>
          {offen && <EinstellungFormular key={offen.schluessel} formular={formular} einstellung={offen} onGespeichert={gespeichert} />}
        </FormularBereich>
      )}

      <section className="abschnitt">
        <h2>Feiertage</h2>
        <p className="leise seitenbeschreibung">
          Gesetzliche Feiertage des Bundeslands werden als „Ganze Werkstatt“-Einträge im{' '}
          <Link to="/abwesenheiten">Abwesenheits-Raster</Link> angelegt – für das laufende und das kommende Jahr automatisch.
          Ein späterer Wechsel des Bundeslands ändert bereits erzeugte Jahre nicht.
        </p>
        {feiertage.jahre.length === 0
          ? <p className="leise">{feiertage.bundesland ? 'Noch keine Feiertage erzeugt.' : 'Bitte zuerst das Bundesland festlegen.'}</p>
          : (
            <dl className={`eckdaten${hervorgehoben === FEIERTAGE ? ' hervorgehoben' : ''}`}>
              {feiertage.jahre.map((j) => (
                <Fragment key={j.jahr}>
                  <dt>{j.jahr}</dt>
                  <dd>{j.anzahl} Feiertage angelegt <span className="leise">({j.bundesland}, erzeugt am {datum(j.erzeugt_am)})</span></dd>
                </Fragment>
              ))}
            </dl>
          )}
        {feiertage.bundesland && (
          <div className="aktionsleiste">
            <AktionsButton formular={formular} schluessel={FEIERTAGE}>Feiertage für ein Jahr erzeugen</AktionsButton>
          </div>
        )}
        {formular.offen === FEIERTAGE && (
          <FormularBereich formular={formular}>
            <FeiertageFormular key={FEIERTAGE} formular={formular} stand={feiertage} onGespeichert={feiertageErzeugt} />
          </FormularBereich>
        )}
        {letztesErgebnis && formular.offen !== FEIERTAGE && (
          <p className="leise">
            Zuletzt für {letztesErgebnis.jahr}:{' '}
            {letztesErgebnis.angelegt.length > 0
              ? `angelegt: ${letztesErgebnis.angelegt.map((t) => `${t.name} (${datum(t.datum)})`).join(', ')}.`
              : 'nichts angelegt.'}
            {letztesErgebnis.uebersprungen.length > 0 && ` Unverändert gelassen: ${letztesErgebnis.uebersprungen.map((t) => t.name).join(', ')}.`}
          </p>
        )}
      </section>
    </>
  )
}
