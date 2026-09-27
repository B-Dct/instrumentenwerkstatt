import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { angemeldeterNutzer, api } from '../api.js'

const instrumentName = (i) =>
  [i.instrumentenklasse_bezeichnung, i.hersteller, i.typenbezeichnung].filter(Boolean).join(' – ')

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

  if (!listen) return fehler ? <p className="fehler">{fehler}</p> : <p>Lädt …</p>

  return (
    <form onSubmit={absenden}>
      <h1>Neuer Auftrag</h1>
      <fieldset>
        <label>Kunde
          <select value={form.kunde_id} onChange={setze('kunde_id')} required>
            <option value="">– bitte wählen –</option>
            {listen.kunden.map((k) => <option key={k.id} value={k.id}>{k.name} ({k.kundennummer})</option>)}
          </select>
        </label>
        <label>Instrument
          <select value={form.instrument_id} onChange={setze('instrument_id')} required disabled={!form.kunde_id}>
            <option value="">{form.kunde_id ? '– bitte wählen –' : '– erst Kunde wählen –'}</option>
            {instrumente.map((i) => <option key={i.id} value={i.id}>{instrumentName(i)}</option>)}
          </select>
        </label>
        <label>Reparaturart
          <select value={form.reparaturart_id} onChange={setze('reparaturart_id')} required>
            <option value="">– bitte wählen –</option>
            {listen.reparaturarten.map((r) => (
              <option key={r.id} value={r.id}>{r.bezeichnung} (Komplexität {r.standard_komplexitaet})</option>
            ))}
          </select>
        </label>
        <label>Zugewiesen an
          <select value={form.zugewiesener_mitarbeiter_id} onChange={setze('zugewiesener_mitarbeiter_id')}>
            <option value="">– noch niemand –</option>
            {listen.mitarbeiter.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <label>Priorität
          <select value={form.prioritaet} onChange={setze('prioritaet')}>
            <option value="normal">normal</option>
            <option value="hoch">hoch</option>
          </select>
        </label>
        <label>Komplexität
          <select value={form.komplexitaet} onChange={setze('komplexitaet')}>
            <option value="">Standard der Reparaturart</option>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label>Notizen <br /><textarea rows={3} value={form.notizen} onChange={setze('notizen')} /></label>
      </fieldset>
      <p>Stunden und Kosten werden beim Anlegen automatisch geschätzt.</p>
      <button disabled={sendet}>{sendet ? 'Wird angelegt …' : 'Auftrag anlegen'}</button>
      {fehler && <p className="fehler">{fehler}</p>}
    </form>
  )
}
