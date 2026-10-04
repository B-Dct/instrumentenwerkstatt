import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { angemeldeterNutzer, api, euro, zahl } from '../api.js'

const instrumentName = (i) =>
  [i.instrumentenklasse_bezeichnung, i.ausfuehrung, i.hersteller, i.typenbezeichnung].filter(Boolean).join(' · ')

export default function AuftragNeu() {
  const navigate = useNavigate()
  const [listen, setListen] = useState(null)
  const [instrumente, setInstrumente] = useState([])
  const [form, setForm] = useState({
    kunde_id: '', instrument_id: '', reparaturart_id: '', ausfuehrung: '',
    zugewiesener_mitarbeiter_id: angemeldeterNutzer()?.id ?? '',
    prioritaet: 'normal', komplexitaet: '', notizen: '',
  })
  const [fehler, setFehler] = useState(null)
  const [sendet, setSendet] = useState(false)

  useEffect(() => {
    // Aktive Kunden für die Auswahl (höchstens 100; eine durchsuchbare Auswahl folgt mit dem Umbau des Formulars)
    Promise.all([api.kunden({ seitengroesse: 100 }).then((seite) => seite.eintraege), api.reparaturarten(), api.mitarbeiter()])
      .then(([kunden, reparaturarten, mitarbeiter]) => setListen({ kunden, reparaturarten, mitarbeiter }))
      .catch((e) => setFehler(e.message))
  }, [])

  useEffect(() => {
    if (form.kunde_id) api.instrumente(form.kunde_id).then(setInstrumente).catch((e) => setFehler(e.message))
  }, [form.kunde_id])

  // Ausführungen (2.5, 2.6a): Hat das Instrument schon eine Ausführung, gilt sie ohne Nachfrage. Sonst erscheint
  // ein Auswahlfeld, wenn es für Reparaturart + Instrumentenklasse mehrere Richtpreise gibt – die Wahl wird
  // am Instrument gespeichert. Ohne Auswahl gilt die Standardausführung.
  const [ausfuehrungen, setAusfuehrungen] = useState([])
  const instrument = instrumente.find((i) => i.id === form.instrument_id)
  const klasseId = instrument?.instrumentenklasse_id
  useEffect(() => {
    let abgebrochen = false
    if (!klasseId || !form.reparaturart_id) return undefined
    api.ausfuehrungen({ reparaturart_id: form.reparaturart_id, instrumentenklasse_id: klasseId })
      .then((liste) => { if (!abgebrochen) setAusfuehrungen(liste) })
      .catch(() => {})
    return () => { abgebrochen = true }
  }, [klasseId, form.reparaturart_id])
  const mehrereAusfuehrungen = klasseId && form.reparaturart_id && ausfuehrungen.length > 1 && !instrument?.ausfuehrung

  const setze = (feld) => (e) => {
    if (feld === 'kunde_id') setInstrumente([])
    // Andere Kombination: die bisherige Auswahl der Ausführung passt nicht mehr
    if (['kunde_id', 'instrument_id', 'reparaturart_id'].includes(feld)) setAusfuehrungen([])
    setForm((f) => ({
      ...f, [feld]: e.target.value,
      ...(feld === 'kunde_id' ? { instrument_id: '' } : {}),
      ...(['kunde_id', 'instrument_id', 'reparaturart_id'].includes(feld) ? { ausfuehrung: '' } : {}),
    }))
  }

  async function absenden(e) {
    e.preventDefault()
    setFehler(null)
    setSendet(true)
    try {
      const auftrag = await api.auftragAnlegen({
        kunde_id: form.kunde_id,
        instrument_id: form.instrument_id,
        reparaturart_id: form.reparaturart_id,
        ausfuehrung: mehrereAusfuehrungen ? form.ausfuehrung || null : null,
        zugewiesener_mitarbeiter_id: form.zugewiesener_mitarbeiter_id || null,
        prioritaet: form.prioritaet,
        komplexitaet: form.komplexitaet ? Number(form.komplexitaet) : null,
        notizen: form.notizen || null,
      })
      navigate(`/auftrag/${auftrag.id}`)
    } catch (err) {
      setFehler(err.message)
      setSendet(false)
    }
  }

  return (
    <>
      <nav className="brotkrumen"><span><Link to="/auftraege">Aufträge</Link></span><span>Neuer Auftrag</span></nav>
      <h1>Neuer Auftrag</h1>
      {!listen && (fehler ? <p className="meldung meldung--fehler">{fehler}</p> : <p className="leise">Lädt …</p>)}
      {listen && (
        <form className="formular" onSubmit={absenden}>
          <label className="feld">
            <span>Kunde</span>
            <select value={form.kunde_id} onChange={setze('kunde_id')} required>
              <option value="">Bitte wählen</option>
              {listen.kunden.map((k) => <option key={k.id} value={k.id}>{k.name} ({k.kundennummer})</option>)}
            </select>
          </label>
          <label className="feld">
            <span>Instrument</span>
            <select value={form.instrument_id} onChange={setze('instrument_id')} required disabled={!form.kunde_id}>
              <option value="">{form.kunde_id ? 'Bitte wählen' : 'Erst Kunde wählen'}</option>
              {instrumente.map((i) => <option key={i.id} value={i.id}>{instrumentName(i)}</option>)}
            </select>
          </label>
          <label className="feld">
            <span>Reparaturart</span>
            <select value={form.reparaturart_id} onChange={setze('reparaturart_id')} required>
              <option value="">Bitte wählen</option>
              {listen.reparaturarten.map((r) => (
                <option key={r.id} value={r.id}>{r.bezeichnung} (Komplexität {r.standard_komplexitaet})</option>
              ))}
            </select>
          </label>
          {mehrereAusfuehrungen && (
            <label className="feld">
              <span>Ausführung</span>
              <select value={form.ausfuehrung} onChange={setze('ausfuehrung')}>
                <option value="">Noch nicht festlegen</option>
                {ausfuehrungen.filter((a) => a.ausfuehrung).map((a) => (
                  <option key={a.ausfuehrung} value={a.ausfuehrung}>
                    {a.ausfuehrung}{a.ist_standard ? ' (Standard)' : ''} – {zahl(a.vorgabe_stunden)} Std., {euro(a.vorgabe_kosten)}
                  </option>
                ))}
              </select>
              <small>Die Auswahl wird am Instrument gespeichert und gilt dann auch für künftige Aufträge. Ohne Auswahl bleibt die Ausführung unbekannt, es gilt der Standard.</small>
            </label>
          )}
          {instrument?.ausfuehrung && (
            <p className="leise">Ausführung: {instrument.ausfuehrung} (am Instrument hinterlegt)</p>
          )}
          <label className="feld">
            <span>Zugewiesen an</span>
            <select value={form.zugewiesener_mitarbeiter_id} onChange={setze('zugewiesener_mitarbeiter_id')}>
              <option value="">Noch niemand</option>
              {listen.mitarbeiter.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </label>
          <div className="spalten spalten--eng">
            <label className="feld">
              <span>Priorität</span>
              <select value={form.prioritaet} onChange={setze('prioritaet')}>
                <option value="normal">Normal</option>
                <option value="hoch">Hoch</option>
              </select>
            </label>
            <label className="feld">
              <span>Komplexität</span>
              <select value={form.komplexitaet} onChange={setze('komplexitaet')}>
                <option value="">Standard der Reparaturart</option>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          <label className="feld">
            <span>Notizen</span>
            <textarea rows={3} value={form.notizen} onChange={setze('notizen')} />
            <small>Nur intern sichtbar.</small>
          </label>
          <p className="leise">Arbeitsstunden und Kosten werden beim Anlegen automatisch geschätzt.</p>
          <button className="btn btn--primaer" disabled={sendet}>{sendet ? 'Wird angelegt …' : 'Auftrag anlegen'}</button>
          {fehler && <p className="meldung meldung--fehler" role="alert">{fehler}</p>}
        </form>
      )}
    </>
  )
}
