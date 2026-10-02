// Werkstatt-Einstellungen (7.5) – nur Admin, nach 9.10: Werte im Lesezustand,
// "… ändern" öffnet das Formular eingebettet. Werte kommen aus einer Auswahl, kein Freitext.
import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, zeit } from '../../api.js'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern, vorabPruefen } from '../../komponenten/speichern.js'

function EinstellungFormular({ formular, einstellung, onGespeichert }) {
  const [wert, setWert] = useState(einstellung.wert ?? '')
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    vorabPruefen({ wert: !wert && 'Bitte auswählen' })
    return api.admin.einstellungSetzen(einstellung.schluessel, wert)
  }, onGespeichert)
  return (
    <FokusFormular formular={formular} titel={`${einstellung.bezeichnung} ${einstellung.wert ? 'ändern' : 'festlegen'}`}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}>
      <Feld label={einstellung.bezeichnung} fehler={felder.wert} hinweis={einstellung.beschreibung}>
        <select value={wert} onChange={(e) => { feldGeaendert('wert'); setWert(e.target.value) }} required>
          <option value="">Bitte wählen</option>
          {einstellung.optionen.map((o) => <option key={o} value={o}>{o}</option>)}
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
  const [fehler, setFehler] = useState(null)

  const laden = useCallback(() => api.admin.einstellungen().then(setEinstellungen).catch((e) => setFehler(e.message)), [])
  useEffect(() => { laden() }, [laden])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!einstellungen) return <p className="leise">Lädt …</p>

  function gespeichert(neu) {
    formular.gespeichert()
    setEinstellungen((alle) => alle.map((e) => (e.schluessel === neu.schluessel ? neu : e)))
    rueckmeldung(`${neu.bezeichnung}: ${neu.wert}`)
    hervorheben(neu.schluessel)
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
              {e.wert ?? <span className="leise">noch nicht festgelegt</span>}
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

      <FormularBereich formular={formular}>
        {offen && <EinstellungFormular key={offen.schluessel} formular={formular} einstellung={offen} onGespeichert={gespeichert} />}
      </FormularBereich>
    </>
  )
}
