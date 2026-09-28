// Vorgabewerte für Dauer und Kosten (2.6a) – nur Admin (7.2), nach 9.10 aufgebaut.
// Ein Wert gilt allgemein für eine Reparaturart oder speziell für eine Instrumentenklasse.
import { useCallback, useEffect, useState } from 'react'
import { api, datum, euro, zahl } from '../../api.js'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { leerZuNull, useSpeichern } from '../../komponenten/speichern.js'

const NEU = 'neu'
const ALLGEMEIN = ''

// Aktive Einträge zur Auswahl; ein bereits verknüpfter archivierter Eintrag bleibt sichtbar
function auswahl(liste, aktuelleId) {
  return liste
    .filter((e) => e.archiviert_am === null || e.id === aktuelleId)
    .map((e) => ({ id: e.id, text: e.archiviert_am ? `${e.bezeichnung} (archiviert)` : e.bezeichnung }))
}

function VorgabewertFormular({ formular, eintrag, arten, klassen, onGespeichert }) {
  const [werte, setWerte] = useState({
    reparaturart_id: eintrag?.reparaturart_id ?? '',
    instrumentenklasse_id: eintrag?.instrumentenklasse_id ?? ALLGEMEIN,
    vorgabe_stunden: eintrag?.vorgabe_stunden ?? '',
    vorgabe_kosten: eintrag?.vorgabe_kosten ?? '',
    notiz: eintrag?.notiz ?? '',
  })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const daten = {
      reparaturart_id: werte.reparaturart_id || null,
      instrumentenklasse_id: werte.instrumentenklasse_id || null,
      vorgabe_stunden: werte.vorgabe_stunden === '' ? null : Number(werte.vorgabe_stunden),
      vorgabe_kosten: werte.vorgabe_kosten === '' ? null : Number(werte.vorgabe_kosten),
      notiz: leerZuNull(werte.notiz),
    }
    return eintrag ? api.admin.vorgabewertAendern(eintrag.id, daten) : api.admin.vorgabewertAnlegen(daten)
  }, onGespeichert, { konfliktFeld: 'instrumentenklasse_id' })
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  return (
    <FokusFormular formular={formular} titel={eintrag ? 'Vorgabewert bearbeiten' : 'Neuer Vorgabewert'}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText={eintrag ? 'Speichern' : 'Vorgabewert anlegen'}>
      <div className="spalten spalten--eng">
        <Feld label="Reparaturart" fehler={felder.reparaturart_id}>
          <select value={werte.reparaturart_id} onChange={setze('reparaturart_id')} required>
            <option value="">Bitte wählen</option>
            {auswahl(arten, eintrag?.reparaturart_id).map((a) => <option key={a.id} value={a.id}>{a.text}</option>)}
          </select>
        </Feld>
        <Feld label="Gilt für" fehler={felder.instrumentenklasse_id}
              hinweis="Ein spezieller Wert hat Vorrang vor dem allgemeinen">
          <select value={werte.instrumentenklasse_id} onChange={setze('instrumentenklasse_id')}>
            <option value={ALLGEMEIN}>Allgemein (alle Instrumentenklassen)</option>
            {auswahl(klassen, eintrag?.instrumentenklasse_id).map((k) => <option key={k.id} value={k.id}>nur {k.text}</option>)}
          </select>
        </Feld>
        <Feld label="Arbeitsstunden" fehler={felder.vorgabe_stunden}>
          <input type="number" min="0" step="0.25" value={werte.vorgabe_stunden} onChange={setze('vorgabe_stunden')} required />
        </Feld>
        <Feld label="Kosten in Euro" fehler={felder.vorgabe_kosten} hinweis="Preis für den Kunden inkl. üblicher Materialpauschale">
          <input type="number" min="0" step="0.01" value={werte.vorgabe_kosten} onChange={setze('vorgabe_kosten')} required />
        </Feld>
      </div>
      <Feld label="Notiz" fehler={felder.notiz} hinweis="Optional, z. B. „inkl. Standardsaiten“">
        <input value={werte.notiz} onChange={setze('notiz')} autoComplete="off" />
      </Feld>
    </FokusFormular>
  )
}

export default function Vorgabewerte() {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [filterArt, setFilterArt] = useState('')
  const [eintraege, setEintraege] = useState(null)
  const [arten, setArten] = useState([])
  const [klassen, setKlassen] = useState([])
  const [fehler, setFehler] = useState(null)

  const neuLaden = useCallback(
    () => api.admin.vorgabewerte(filterArt ? { reparaturart_id: filterArt } : {})
      .then(setEintraege).catch((e) => setFehler(e.message)),
    [filterArt],
  )
  useEffect(() => { neuLaden() }, [neuLaden])
  useEffect(() => {
    Promise.all([api.admin.arten(true), api.admin.klassen(true)])
      .then(([a, k]) => { setArten(a); setKlassen(k) })
      .catch((e) => setFehler(e.message))
  }, [])

  const archiviert = (liste, id) => liste.find((e) => e.id === id)?.archiviert_am != null

  async function gespeichert(eintrag, neu) {
    formular.gespeichert()
    const fuer = eintrag.instrumentenklasse_bezeichnung ?? 'allgemein'
    rueckmeldung(`Vorgabewert ${eintrag.reparaturart_bezeichnung} (${fuer}) ${neu ? 'angelegt' : 'gespeichert'}`)
    await neuLaden()
    hervorheben(eintrag.id)
  }

  const offenerEintrag = eintraege?.find((e) => e.id === formular.offen)

  return (
    <>
      <div className="kopf"><h1>Vorgabewerte</h1></div>
      <p className="leise seitenbeschreibung">
        Erwartete Arbeitsstunden und Kosten je Reparaturart. Sie gelten, solange es weniger als fünf abgeschlossene
        Vergleichsaufträge gibt; danach rechnet die Schätzung mit dem historischen Durchschnitt.
      </p>

      <div className="aktionsleiste">
        <AktionsButton formular={formular} schluessel={NEU} primaer>Neuer Vorgabewert</AktionsButton>
      </div>
      <FormularBereich formular={formular}>
        {formular.offen === NEU && (
          <VorgabewertFormular key={NEU} formular={formular} arten={arten} klassen={klassen}
                               onGespeichert={(e) => gespeichert(e, true)} />
        )}
        {offenerEintrag && (
          <VorgabewertFormular key={offenerEintrag.id} formular={formular} eintrag={offenerEintrag}
                               arten={arten} klassen={klassen} onGespeichert={(e) => gespeichert(e, false)} />
        )}
      </FormularBereich>

      <div className="filterleiste">
        <label className="feld feld--inline">
          <span>Reparaturart</span>
          <select value={filterArt} onChange={(e) => { setEintraege(null); setFilterArt(e.target.value) }}>
            <option value="">alle</option>
            {arten.map((a) => <option key={a.id} value={a.id}>{a.bezeichnung}{a.archiviert_am ? ' (archiviert)' : ''}</option>)}
          </select>
        </label>
      </div>

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {eintraege === null && !fehler && <p className="leise">Lädt …</p>}
      {eintraege?.length === 0 && <p className="leise">Keine Vorgabewerte vorhanden.</p>}
      {eintraege?.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr><th>Reparaturart</th><th>Gilt für</th><th className="zahl">Std.</th><th className="zahl">Kosten</th><th>Notiz</th><th>Geändert</th></tr>
            </thead>
            <tbody>
              {eintraege.map((e) => (
                <tr key={e.id} onClick={() => formular.oeffnen(e.id)}
                    className={[e.id === hervorgehoben && 'zeile--hervorgehoben', formular.offen === e.id && 'zeile--ausgewaehlt']
                      .filter(Boolean).join(' ') || undefined}>
                  <td>
                    <button type="button" className="link-button" aria-expanded={formular.offen === e.id}
                            onClick={(ev) => { ev.stopPropagation(); formular.oeffnen(e.id) }}>
                      {e.reparaturart_bezeichnung}
                    </button>
                    {archiviert(arten, e.reparaturart_id) && <span className="marke">archiviert</span>}
                  </td>
                  <td>
                    {e.instrumentenklasse_bezeichnung ?? <span className="leise">allgemein</span>}
                    {archiviert(klassen, e.instrumentenklasse_id) && <span className="marke">archiviert</span>}
                  </td>
                  <td className="zahl">{zahl(e.vorgabe_stunden)}</td>
                  <td className="zahl">{euro(e.vorgabe_kosten)}</td>
                  <td>{e.notiz ?? ''}</td>
                  <td>{datum(e.geaendert_am)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
