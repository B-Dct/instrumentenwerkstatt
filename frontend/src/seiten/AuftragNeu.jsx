import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { angemeldeterNutzer, api } from '../api.js'

const instrumentName = (i) =>
  [i.instrumentenklasse_bezeichnung, i.hersteller, i.typenbezeichnung].filter(Boolean).join(' · ')

export default function AuftragNeu() {
  const navigate = useNavigate()
  const [listen, setListen] = useState(null)
  const [instrumente, setInstrumente] = useState([])
  const [form, setForm] = useState({
    kunde_id: '', instrument_id: '', reparaturart_id: '',
    zugewiesener_mitarbeiter_id: angemeldeterNutzer()?.id ?? '',
    prioritaet: 'normal', komplexitaet: '', notizen: '',
  })
  const [fehler, setFehler] = useState(null)
  const [sendet, setSendet] = useState(false)

  useEffect(() => {
    Promise.all([api.kunden(), api.reparaturarten(), api.mitarbeiter()])
      .then(([kunden, reparaturarten, mitarbeiter]) => setListen({ kunden, reparaturarten, mitarbeiter }))
      .catch((e) => setFehler(e.message))
  }, [])

  useEffect(() => {
    if (form.kunde_id) api.instrumente(form.kunde_id).then(setInstrumente).catch((e) => setFehler(e.message))
  }, [form.kunde_id])

  const setze = (feld) => (e) => {
    if (feld === 'kunde_id') setInstrumente([])
    setForm((f) => ({ ...f, [feld]: e.target.value, ...(feld === 'kunde_id' ? { instrument_id: '' } : {}) }))
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
      <nav className="brotkrumen"><span><Link to="/">Aufträge</Link></span><span>Neuer Auftrag</span></nav>
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
