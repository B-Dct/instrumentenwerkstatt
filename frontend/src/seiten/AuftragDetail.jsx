import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { api, datum, euro, stunden, zeit } from '../api.js'
import { HohePrioritaet, Status, Ueberfaellig } from '../komponenten/Status.jsx'
import { istUeberfaellig } from '../komponenten/ueberfaellig.js'

const QUELLEN = {
  historisch: 'historischer Durchschnitt',
  vorgabe_instrumentenklasse: 'Vorgabewert der Instrumentenklasse',
  vorgabe_allgemein: 'allgemeiner Vorgabewert',
  keine: 'keine Grundlage',
}
const METHODEN = { regelbasiert: 'Automatisch', manuelle_korrektur: 'Korrektur' }

function quelleText(eintrag) {
  const f = eintrag.eingabefaktoren
  if (eintrag.methode !== 'regelbasiert' || !f) return null
  const teil = (x) => `${QUELLEN[x.quelle] ?? x.quelle} (${x.anzahl_vergleichsfaelle} Vergleichsfälle)`
  return `Stunden: ${teil(f.stunden)}. Kosten: ${teil(f.kosten)}.`
}

function Meldung({ meldung }) {
  if (!meldung) return null
  return (
    <p className={`meldung ${meldung.ok ? 'meldung--erfolg' : 'meldung--fehler'}`} role={meldung.ok ? 'status' : 'alert'}>
      {meldung.text}
    </p>
  )
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
      setMeldung({ ok: true, text: `Status geändert: ${neu.status.bezeichnung}` })
      onFertig(neu)
    } catch (err) {
      setMeldung({ ok: false, text: err.message })
    }
  }

  return (
    <form onSubmit={absenden}>
      <h2>Status ändern</h2>
      <label className="feld">
        <span>Neuer Status</span>
        <select value={statusId} onChange={(e) => setStatusId(e.target.value)} required>
          <option value="">Bitte wählen</option>
          {alleStatus.filter((s) => s.id !== auftrag.status.id).map((s) => (
            <option key={s.id} value={s.id}>{s.symbol} {s.bezeichnung}</option>
          ))}
        </select>
      </label>
      {ziel?.erfordert_zeiterfassung && (
        <label className="feld">
          <span>Aufgewendete Arbeitszeit in Minuten</span>
          <input type="number" min="1" value={minuten} onChange={(e) => setMinuten(e.target.value)} required />
          <small>Pflichtangabe beim Abschluss.</small>
        </label>
      )}
      <label className="feld">
        <span>Kommentar</span>
        <input value={kommentar} onChange={(e) => setKommentar(e.target.value)} />
      </label>
      <button className="btn btn--primaer">Status ändern</button>
      <Meldung meldung={meldung} />
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
      <h2>Schätzung korrigieren</h2>
      <div className="spalten spalten--eng">
        <label className="feld">
          <span>Arbeitsstunden</span>
          <input type="number" min="0" step="0.25" value={std} onChange={(e) => setStd(e.target.value)} />
          <small>Aktuell {stunden(auftrag.geschaetzte_arbeitsstunden)}</small>
        </label>
        <label className="feld">
          <span>Kosten in Euro</span>
          <input type="number" min="0" step="0.01" value={kosten} onChange={(e) => setKosten(e.target.value)} />
          <small>Aktuell {euro(auftrag.geschaetzte_kosten)}</small>
        </label>
      </div>
      <label className="feld">
        <span>Begründung</span>
        <textarea rows={2} value={grund} onChange={(e) => setGrund(e.target.value)} required />
        <small>Pflichtangabe, wird im Protokoll gespeichert.</small>
      </label>
      <button className="btn btn--sekundaer">Korrektur speichern</button>
      <Meldung meldung={meldung} />
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

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!auftrag) return <p className="leise">Lädt …</p>

  return (
    <>
      <nav className="brotkrumen"><span><Link to="/">Aufträge</Link></span><span>{auftrag.auftragsnummer}</span></nav>
      <div className="kopf">
        <h1>Auftrag {auftrag.auftragsnummer}</h1>
        <Status status={auftrag.status} />
        {istUeberfaellig(auftrag) && <Ueberfaellig />}
        {auftrag.prioritaet === 'hoch' && <HohePrioritaet />}
      </div>

      <dl className="eckdaten">
        <dt>Kunde</dt><dd>{auftrag.kunde_name}</dd>
        <dt>Instrument</dt><dd>{auftrag.instrumentenklasse_bezeichnung}</dd>
        <dt>Reparatur</dt><dd>{auftrag.reparaturart_bezeichnung} (Komplexität {auftrag.komplexitaet})</dd>
        <dt>Zugewiesen an</dt><dd>{auftrag.zugewiesener_mitarbeiter_name ?? 'nicht zugewiesen'}</dd>
        <dt>Geschätzt</dt><dd>{stunden(auftrag.geschaetzte_arbeitsstunden)} · {euro(auftrag.geschaetzte_kosten)}</dd>
        <dt>Voraussichtlich fertig</dt><dd>{datum(auftrag.geschaetztes_fertigstellungsdatum)}</dd>
        <dt>Eingang</dt><dd>{zeit(auftrag.erstellt_am)}</dd>
        <dt>Fertiggestellt am</dt><dd>{datum(auftrag.tatsaechliches_fertigstellungsdatum)}</dd>
        <dt>Zugangscode Kunde</dt><dd><code>{auftrag.zugriffstoken}</code></dd>
        {auftrag.notizen && <><dt>Notizen</dt><dd>{auftrag.notizen}</dd></>}
      </dl>

      <section className="abschnitt spalten">
        <Statuswechsel auftrag={auftrag} alleStatus={alleStatus} onFertig={setAuftrag} />
        <Korrektur auftrag={auftrag} onFertig={setAuftrag} />
      </section>

      <section className="abschnitt">
        <h2>Statusverlauf</h2>
        <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead><tr><th>Zeitpunkt</th><th>Status</th><th>Von</th><th>Kommentar</th></tr></thead>
          <tbody>
            {auftrag.statusverlauf.map((v, i) => (
              <tr key={i}>
                <td>{zeit(v.geaendert_am)}</td>
                <td><Status status={v.status} /></td>
                <td>{name(v.geaendert_von_mitarbeiter_id)}</td>
                <td>{v.kommentar ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>

      <section className="abschnitt">
        <h2>Schätzungen</h2>
        <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead>
            <tr><th>Zeitpunkt</th><th>Art</th><th className="zahl">Stunden</th><th className="zahl">Kosten</th><th>Grundlage</th></tr>
          </thead>
          <tbody>
            {auftrag.schaetzungen.map((s) => (
              <tr key={s.id}>
                <td>{zeit(s.berechnet_am)}</td>
                <td>{METHODEN[s.methode] ?? s.methode}</td>
                <td className="zahl">{stunden(s.geschaetzte_stunden)}</td>
                <td className="zahl">{euro(s.geschaetzte_kosten)}</td>
                <td>
                  {quelleText(s)}
                  {s.methode === 'manuelle_korrektur' && <>{name(s.korrigiert_von_mitarbeiter_id)}: „{s.grund}“</>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>
    </>
  )
}
