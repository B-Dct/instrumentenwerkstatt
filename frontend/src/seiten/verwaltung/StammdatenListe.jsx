// Gemeinsame Seite für einfache Stammdaten (Instrumentenklassen, Reparaturarten) nach 9.10/9.11:
// Liste im Vordergrund (Suche, Status-Filter, Sortierung, Seiten über den Listen-Baustein),
// "Neu" oder Klick auf eine Zeile öffnet das Formular eingebettet,
// Archivieren/Reaktivieren als Zeilenaktion (nie als Löschen).
import { useState } from 'react'
import { AktionsButton, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { ListeLeer, Listenkopf, Seitenwahl, SortierKopf } from '../../komponenten/Liste.jsx'
import { useListe } from '../../komponenten/liste.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { useSpeichern } from '../../komponenten/speichern.js'

const NEU = 'neu'

// Die ganze Seite ist nur für Admins (7.2), daher sehen alle hier den Status-Filter
const FILTER = [
  { name: 'status', label: 'Status', standard: 'aktiv', optionen: [
    { wert: 'aktiv', text: 'aktiv' }, { wert: 'archiviert', text: 'archiviert' }, { wert: 'alle', text: 'alle' },
  ] },
]

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

// spalten: [{ titel, spalte (Sortierschlüssel im Backend), wert, zahl? }]
export default function StammdatenListe({ text, laden, anlegen, aendern, archivieren, reaktivieren,
                                          spalten, sortierung, suchhinweis, startwerte, zuDaten, Felder }) {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [aktionsfehler, setAktionsfehler] = useState(null)
  const liste = useListe({ laden, filter: FILTER, sortierung })
  const { daten, fehler } = liste
  const eintraege = daten?.eintraege

  function gespeichert(eintrag, neu) {
    formular.gespeichert()
    rueckmeldung(`${text.einzahl} „${eintrag.bezeichnung}“ ${neu ? 'angelegt' : 'gespeichert'}`)
    liste.neuLaden()
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
      liste.neuLaden()
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

      <Listenkopf liste={liste} suchhinweis={suchhinweis} />

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {!daten && !fehler && <p className="leise">Lädt …</p>}
      <ListeLeer liste={liste} leerText={text.leer} />
      {eintraege?.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr>
                {spalten.map((s) => <SortierKopf key={s.spalte} liste={liste} spalte={s.spalte} zahl={s.zahl}>{s.titel}</SortierKopf>)}
                <th></th>
              </tr>
            </thead>
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
      <Seitenwahl liste={liste} />
    </>
  )
}
