import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { api, datum, euro, stunden, zeit } from '../api.js'
import { StatusMarke } from './AuftragListe.jsx'

const QUELLEN = {
  historisch: 'historischer Durchschnitt',
  vorgabe_instrumentenklasse: 'Vorgabewert (Instrumentenklasse)',
  vorgabe_allgemein: 'Vorgabewert (allgemein)',
  keine: 'keine Grundlage',
}

function quelleText(eintrag) {
  const f = eintrag.eingabefaktoren
  if (eintrag.methode !== 'regelbasiert' || !f) return null
  const teil = (x) => `${QUELLEN[x.quelle] ?? x.quelle}, ${x.anzahl_vergleichsfaelle} Vergleichsfälle`
  return `Stunden: ${teil(f.stunden)} · Kosten: ${teil(f.kosten)}`
}

function Statuswechsel({ auftrag, alleStatus, onFertig }) {
  const [statusId, setStatusId] = useState('')
  const [kommentar, setKommentar] = useState('')
  const [minuten, setMinuten] = useState('')
  const [meldung, setMeldung] = useState(null)
  const ziel = alleStatus.find((s) => s.id === statusId)

  async function absenden(e) {
    e.preventDefault()
    setMeldung(null)
    try {
      const neu = await api.statusWechseln(auftrag.id, {
        status_id: statusId,
        kommentar: kommentar || null,
        arbeitszeit_minuten: minuten ? Number(minuten) : null,
      })
      setStatusId(''); setKommentar(''); setMinuten('')
      setMeldung({ ok: true, text: `Status geändert auf „${neu.status.bezeichnung}“` })
      onFertig(neu)
    } catch (err) {
      setMeldung({ ok: false, text: err.message })
    }
  }

  return (
    <form onSubmit={absenden}>
      <fieldset>
        <legend>Status wechseln</legend>
        <label>Neuer Status
          <select value={statusId} onChange={(e) => setStatusId(e.target.value)} required>
            <option value="">– bitte wählen –</option>
            {alleStatus.filter((s) => s.id !== auftrag.status.id).map((s) => (
              <option key={s.id} value={s.id}>{s.bezeichnung}</option>
            ))}
          </select>
        </label>
        {ziel?.erfordert_zeiterfassung && (
          <label>Aufgewendete Arbeitszeit (Minuten, Pflicht)
            <input type="number" min="1" value={minuten} onChange={(e) => setMinuten(e.target.value)} required />
          </label>
        )}
        <label>Kommentar <input value={kommentar} onChange={(e) => setKommentar(e.target.value)} /></label>
        <button>Status ändern</button>
        {meldung && <p className={meldung.ok ? 'erfolg' : 'fehler'}>{meldung.text}</p>}
      </fieldset>
    </form>
  )
}

function Korrektur({ auftrag, onFertig }) {
  const [std, setStd] = useState('')
  const [kosten, setKosten] = useState('')
  const [grund, setGrund] = useState('')
  const [meldung, setMeldung] = useState(null)

  async function absenden(e) {
    e.preventDefault()
    setMeldung(null)
    try {
      const neu = await api.schaetzungKorrigieren(auftrag.id, {
        geschaetzte_arbeitsstunden: std ? Number(std) : null,
        geschaetzte_kosten: kosten ? Number(kosten) : null,
        grund,
      })
      setStd(''); setKosten(''); setGrund('')
      setMeldung({ ok: true, text: 'Schätzung korrigiert' })
      onFertig(neu)
    } catch (err) {
      setMeldung({ ok: false, text: err.message })
    }
  }

  return (
    <form onSubmit={absenden}>
      <fieldset>
        <legend>Schätzung korrigieren</legend>
        <label>Stunden (aktuell {stunden(auftrag.geschaetzte_arbeitsstunden)})
          <input type="number" min="0" step="0.25" value={std} onChange={(e) => setStd(e.target.value)} />
        </label>
        <label>Kosten in € (aktuell {euro(auftrag.geschaetzte_kosten)})
          <input type="number" min="0" step="0.01" value={kosten} onChange={(e) => setKosten(e.target.value)} />
        </label>
        <label>Begründung (Pflicht)<br />
          <textarea rows={2} value={grund} onChange={(e) => setGrund(e.target.value)} required />
        </label>
        <button>Korrektur speichern</button>
        {meldung && <p className={meldung.ok ? 'erfolg' : 'fehler'}>{meldung.text}</p>}
      </fieldset>
    </form>
  )
}

export default function AuftragDetail() {
  const { id } = useParams()
  const [auftrag, setAuftrag] = useState(null)
  const [alleStatus, setAlleStatus] = useState([])
  const [namen, setNamen] = useState({})
  const [fehler, setFehler] = useState(null)

  const laden = useCallback(() => {
    api.auftrag(id).then(setAuftrag).catch((e) => setFehler(e.message))
  }, [id])

  useEffect(() => {
    laden()
    api.auftragsstatus().then(setAlleStatus).catch((e) => setFehler(e.message))
    api.mitarbeiter()
      .then((liste) => setNamen(Object.fromEntries(liste.map((m) => [m.id, m.name]))))
      .catch(() => {})
  }, [laden])

  const name = (mitarbeiterId) => (mitarbeiterId ? namen[mitarbeiterId] ?? 'unbekannt' : '–')

  if (fehler) return <p className="fehler">{fehler}</p>
  if (!auftrag) return <p>Lädt …</p>

  return (
    <>
      <p><Link to="/">← Aufträge</Link></p>
      <h1>Auftrag {auftrag.auftragsnummer} <StatusMarke status={auftrag.status} /></h1>

      <table>
        <tbody>
          <tr><th>Kunde</th><td>{auftrag.kunde_name}</td></tr>
          <tr><th>Instrument</th><td>{auftrag.instrumentenklasse_bezeichnung}</td></tr>
          <tr><th>Reparatur</th><td>{auftrag.reparaturart_bezeichnung}</td></tr>
          <tr><th>Zugewiesen an</th><td>{auftrag.zugewiesener_mitarbeiter_name ?? '–'}</td></tr>
          <tr><th>Priorität / Komplexität</th><td>{auftrag.prioritaet} / {auftrag.komplexitaet}</td></tr>
          <tr><th>Geschätzt</th><td>{stunden(auftrag.geschaetzte_arbeitsstunden)} / {euro(auftrag.geschaetzte_kosten)}</td></tr>
          <tr><th>Eingang</th><td>{zeit(auftrag.erstellt_am)}</td></tr>
          <tr><th>Fertiggestellt am</th><td>{datum(auftrag.tatsaechliches_fertigstellungsdatum)}</td></tr>
          <tr><th>Zugangscode Kunde</th><td><code>{auftrag.zugriffstoken}</code></td></tr>
          <tr><th>Notizen</th><td>{auftrag.notizen ?? '–'}</td></tr>
        </tbody>
      </table>

      <Statuswechsel auftrag={auftrag} alleStatus={alleStatus} onFertig={setAuftrag} />
      <Korrektur auftrag={auftrag} onFertig={setAuftrag} />

      <h2>Statusverlauf</h2>
      <table>
        <thead><tr><th>Zeitpunkt</th><th>Status</th><th>Von</th><th>Kommentar</th></tr></thead>
        <tbody>
          {auftrag.statusverlauf.map((v, i) => (
            <tr key={i}>
              <td>{zeit(v.geaendert_am)}</td>
              <td><StatusMarke status={v.status} /></td>
              <td>{name(v.geaendert_von_mitarbeiter_id)}</td>
              <td>{v.kommentar ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Schätzungen (Protokoll)</h2>
      <table>
        <thead><tr><th>Zeitpunkt</th><th>Methode</th><th>Stunden</th><th>Kosten</th><th>Details</th></tr></thead>
        <tbody>
          {auftrag.schaetzungen.map((s) => (
            <tr key={s.id}>
              <td>{zeit(s.berechnet_am)}</td>
              <td>{s.methode}</td>
              <td>{stunden(s.geschaetzte_stunden)}</td>
              <td>{euro(s.geschaetzte_kosten)}</td>
              <td>
                {quelleText(s)}
                {s.methode === 'manuelle_korrektur' && <>von {name(s.korrigiert_von_mitarbeiter_id)}: „{s.grund}“</>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
