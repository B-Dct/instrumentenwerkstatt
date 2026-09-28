// Gemeinsame Seite für einfache Stammdaten (Instrumentenklassen, Reparaturarten) nach 9.10:
// Liste im Vordergrund, "Neu" oder Klick auf eine Zeile öffnet das Formular eingebettet,
// Archivieren/Reaktivieren als Zeilenaktion (nie als Löschen).
import { useCallback, useEffect, useState } from 'react'
import { AktionsButton, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern } from '../../komponenten/speichern.js'

const NEU = 'neu'

function EintragFormular({ formular, eintrag, text, anlegen, aendern, startwerte, zuDaten, Felder, onGespeichert }) {
  const [werte, setWerte] = useState(startwerte(eintrag))
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(
    () => (eintrag ? aendern(eintrag.id, zuDaten(werte)) : anlegen(zuDaten(werte))),
    onGespeichert,
    { konfliktFeld: 'bezeichnung' },
  )
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }
  return (
    <FokusFormular formular={formular} titel={eintrag ? `${text.einzahl} bearbeiten` : text.neu}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText={eintrag ? 'Speichern' : `${text.einzahl} anlegen`}>
      <Felder werte={werte} setze={setze} felder={felder} />
    </FokusFormular>
  )
}

export default function StammdatenListe({ text, laden, anlegen, aendern, archivieren, reaktivieren,
                                          spalten, startwerte, zuDaten, Felder }) {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [archivierte, setArchivierte] = useState(false)
  const [eintraege, setEintraege] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [aktionsfehler, setAktionsfehler] = useState(null)

  const neuLaden = useCallback(
    () => laden(archivierte).then(setEintraege).catch((e) => setFehler(e.message)),
    [laden, archivierte],
  )
  useEffect(() => { neuLaden() }, [neuLaden])

  async function gespeichert(eintrag, neu) {
    formular.gespeichert()
    rueckmeldung(`${text.einzahl} „${eintrag.bezeichnung}“ ${neu ? 'angelegt' : 'gespeichert'}`)
    await neuLaden()
    hervorheben(eintrag.id)
  }

  async function archivStatus(eintrag, archiv) {
    setAktionsfehler(null)
    if (formular.geaendert) {
      setAktionsfehler('Bitte das offene Formular zuerst speichern oder abbrechen.')
      return
    }
    formular.gespeichert()
    try {
      await (archiv ? archivieren(eintrag.id) : reaktivieren(eintrag.id))
      rueckmeldung(archiv
        ? `„${eintrag.bezeichnung}“ archiviert – bleibt für bestehende Daten erhalten und kann reaktiviert werden`
        : `„${eintrag.bezeichnung}“ reaktiviert`)
      await neuLaden()
      hervorheben(eintrag.id)
    } catch (err) {
      setAktionsfehler(err.message)
    }
  }

  const offenerEintrag = eintraege?.find((e) => e.id === formular.offen)
  const formularProps = { formular, text, anlegen, aendern, startwerte, zuDaten, Felder }

  return (
    <>
      <div className="kopf"><h1>{text.titel}</h1></div>
      {text.beschreibung && <p className="leise seitenbeschreibung">{text.beschreibung}</p>}

      <div className="aktionsleiste">
        <AktionsButton formular={formular} schluessel={NEU} primaer>{text.neu}</AktionsButton>
      </div>
      {aktionsfehler && <p className="meldung meldung--fehler" role="alert">{aktionsfehler}</p>}
      <FormularBereich formular={formular}>
        {formular.offen === NEU && (
          <EintragFormular key={NEU} {...formularProps} eintrag={null} onGespeichert={(e) => gespeichert(e, true)} />
        )}
        {offenerEintrag && (
          <EintragFormular key={offenerEintrag.id} {...formularProps} eintrag={offenerEintrag}
                           onGespeichert={(e) => gespeichert(e, false)} />
        )}
      </FormularBereich>

      <div className="filterleiste">
        <label className="feld--inline leise">
          <input type="checkbox" checked={archivierte} onChange={(e) => setArchivierte(e.target.checked)} />
          archivierte anzeigen
        </label>
      </div>

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {eintraege === null && !fehler && <p className="leise">Lädt …</p>}
      {eintraege?.length === 0 && <p className="leise">{text.leer}</p>}
      {eintraege?.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead><tr>{spalten.map((s) => <th key={s.titel} className={s.zahl ? 'zahl' : undefined}>{s.titel}</th>)}<th></th></tr></thead>
            <tbody>
              {eintraege.map((e) => {
                const archiviert = e.archiviert_am !== null
                return (
                  <tr key={e.id}
                      className={[e.id === hervorgehoben && 'zeile--hervorgehoben', archiviert && 'zeile--archiviert zeile--nicht-klickbar',
                        formular.offen === e.id && 'zeile--ausgewaehlt'].filter(Boolean).join(' ') || undefined}
                      onClick={archiviert ? undefined : () => formular.oeffnen(e.id)}>
                    {spalten.map((s, i) => (
                      <td key={s.titel} className={s.zahl ? 'zahl' : undefined}>
                        {i === 0 && !archiviert
                          ? <button type="button" className="link-button" aria-expanded={formular.offen === e.id}
                                    onClick={(ev) => { ev.stopPropagation(); formular.oeffnen(e.id) }}>{s.wert(e)}</button>
                          : s.wert(e)}
                      </td>
                    ))}
                    <td className="zeilenaktionen">
                      {archiviert && <span className="marke">archiviert</span>}
                      <button type="button" className={`btn btn--klein ${archiviert ? 'btn--sekundaer' : 'btn--gefahr'}`}
                              onClick={(ev) => { ev.stopPropagation(); archivStatus(e, !archiviert) }}>
                        {archiviert ? 'Reaktivieren' : 'Archivieren'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
