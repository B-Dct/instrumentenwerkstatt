// Auftragsdetailseite nach 9.10: Kopf und Eckdaten im Lesezustand, feste Aktionsleiste,
// jede Aktion öffnet ihr Formular eingebettet darunter (nur eins gleichzeitig).
// Statusverlauf, Unterbrechungen und Schätzungen sind zugeklappte Lese-Bereiche.
// Berechtigungen (7.2) prüft das Backend; die Oberfläche zeigt nur erlaubte Aktionen.
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { angemeldeterNutzer, api, datum, euro, hatRolle, stunden, zahl, zeit } from '../api.js'
import Aufklappbereich from '../komponenten/Aufklappbereich.jsx'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../komponenten/fokusFormular.js'
import { useHervorhebung } from '../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../komponenten/rueckmeldung.js'
import { leerZuNull, useSpeichern, vorabPruefen } from '../komponenten/speichern.js'
import { HohePrioritaet, Status, Ueberfaellig } from '../komponenten/Status.jsx'

const STATUS = 'status'
const KORREKTUR = 'korrektur'
const TERMIN = 'termin'
const ZUWEISUNG = 'zuweisung'

const QUELLEN = {
  historisch: 'historischer Durchschnitt',
  vorgabe_instrumentenklasse: 'Vorgabewert der Instrumentenklasse',
  vorgabe_allgemein: 'allgemeiner Vorgabewert',
  keine: 'keine Grundlage',
}
const METHODEN = { regelbasiert: 'Automatisch', manuelle_korrektur: 'Korrektur' }
const ANLAESSE = {
  auftrag_angelegt: 'beim Anlegen',
  zuweisung_geaendert: 'nach Umzuweisung',
  prioritaet_geaendert: 'nach Prioritätsänderung',
  'zuweisung_geaendert+prioritaet_geaendert': 'nach Umzuweisung und Prioritätsänderung',
}

function quelleText(eintrag) {
  const f = eintrag.eingabefaktoren
  if (eintrag.methode !== 'regelbasiert' || !f) return null
  const teile = []
  if (f.anlass) teile.push(`Berechnet ${ANLAESSE[f.anlass] ?? f.anlass}.`)
  const teil = (x) => `${QUELLEN[x.quelle] ?? x.quelle} (${x.anzahl_vergleichsfaelle} Vergleichsfälle)`
  if (f.stunden) teile.push(`Stunden: ${teil(f.stunden)}. Kosten: ${teil(f.kosten)}.`)
  const t = f.termin
  if (t?.arbeitstage != null) {
    const vorlauf = t.ohne_zuweisung ? 'durchschnittliche Warteschlange' : `${t.auftraege_davor} Aufträge davor`
    const z = (wert) => zahl(Number(wert))
    teile.push(`Termin: ${z(t.warteschlange_stunden)} Std. Vorlauf (${vorlauf}) + ${z(t.eigene_stunden)} Std., ${z(t.stunden_pro_tag)} Std./Tag, ${t.arbeitstage} Arbeitstage.`)
  }
  return teile.join(' ')
}

const anzahl = (n, einzahl, mehrzahl) => `${n} ${n === 1 ? einzahl : mehrzahl}`
// Namen liefert das Backend direkt im Eintrag mit (auch für deaktivierte Mitarbeiter)
const von = (name) => name ?? '–'

// --- Formulare ---------------------------------------------------------------------

function StatusFormular({ formular, auftrag, alleStatus, onGespeichert }) {
  const [werte, setWerte] = useState({ status_id: '', arbeitszeit_minuten: '', unterbrechungsgrund: '', kommentar: '' })
  const ziel = alleStatus.find((s) => s.id === werte.status_id)
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    vorabPruefen({
      status_id: !werte.status_id && 'Bitte auswählen',
      arbeitszeit_minuten: ziel?.erfordert_zeiterfassung && !werte.arbeitszeit_minuten && 'Pflichtangabe beim Abschluss',
    })
    return api.statusWechseln(auftrag.id, {
      status_id: werte.status_id,
      kommentar: leerZuNull(werte.kommentar),
      arbeitszeit_minuten: ziel?.erfordert_zeiterfassung ? Number(werte.arbeitszeit_minuten) : null,
      unterbrechungsgrund: ziel?.unterbrechungsgrund ? leerZuNull(werte.unterbrechungsgrund) : null,
    })
  }, onGespeichert)
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  return (
    <FokusFormular formular={formular} titel="Status ändern" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText="Status ändern">
      <div className="spalten spalten--eng">
        <Feld label="Neuer Status" fehler={felder.status_id} hinweis={`Aktuell: ${auftrag.status.bezeichnung}`}>
          <select value={werte.status_id} onChange={setze('status_id')} required>
            <option value="">Bitte wählen</option>
            {alleStatus.filter((s) => s.id !== auftrag.status.id).map((s) => (
              <option key={s.id} value={s.id}>{s.symbol} {s.bezeichnung}</option>
            ))}
          </select>
        </Feld>
        {ziel?.erfordert_zeiterfassung && (
          <Feld label="Aufgewendete Arbeitszeit in Minuten" fehler={felder.arbeitszeit_minuten} hinweis="Pflichtangabe beim Abschluss">
            <input type="number" min="1" step="1" value={werte.arbeitszeit_minuten} onChange={setze('arbeitszeit_minuten')} required />
          </Feld>
        )}
        {ziel?.unterbrechungsgrund && (
          <Feld label="Grund der Unterbrechung" fehler={felder.unterbrechungsgrund}
                hinweis={`Leer lassen für „${ziel.unterbrechungsgrund}“. Die Wartezeit wird bis zum nächsten Statuswechsel erfasst.`}>
            <input value={werte.unterbrechungsgrund} onChange={setze('unterbrechungsgrund')}
                   placeholder={ziel.unterbrechungsgrund} maxLength={200} autoComplete="off" />
          </Feld>
        )}
      </div>
      <Feld label="Kommentar" fehler={felder.kommentar} hinweis="Optional, erscheint im Statusverlauf">
        <input value={werte.kommentar} onChange={setze('kommentar')} autoComplete="off" />
      </Feld>
    </FokusFormular>
  )
}

function KorrekturFormular({ formular, auftrag, onGespeichert }) {
  const [werte, setWerte] = useState({ geschaetzte_arbeitsstunden: '', geschaetzte_kosten: '', grund: '' })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const keinWert = !werte.geschaetzte_arbeitsstunden && !werte.geschaetzte_kosten
    vorabPruefen({
      geschaetzte_arbeitsstunden: keinWert && 'Stunden oder Kosten angeben',
      geschaetzte_kosten: keinWert && 'Stunden oder Kosten angeben',
      grund: !werte.grund.trim() && 'Pflichtangabe, wird im Protokoll gespeichert',
    })
    return api.schaetzungKorrigieren(auftrag.id, {
      geschaetzte_arbeitsstunden: werte.geschaetzte_arbeitsstunden === '' ? null : Number(werte.geschaetzte_arbeitsstunden),
      geschaetzte_kosten: werte.geschaetzte_kosten === '' ? null : Number(werte.geschaetzte_kosten),
      grund: werte.grund,
    })
  }, onGespeichert)
  // Stunden/Kosten gehören zusammen: Eingabe in einem Feld löscht den gemeinsamen Hinweis an beiden
  const setze = (feld) => (e) => {
    feldGeaendert(feld)
    if (feld !== 'grund') feldGeaendert(feld === 'geschaetzte_kosten' ? 'geschaetzte_arbeitsstunden' : 'geschaetzte_kosten')
    setWerte((w) => ({ ...w, [feld]: e.target.value }))
  }

  return (
    <FokusFormular formular={formular} titel="Schätzung korrigieren" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText="Korrektur speichern">
      <div className="spalten spalten--eng">
        <Feld label="Arbeitsstunden" fehler={felder.geschaetzte_arbeitsstunden}
              hinweis={`Aktuell ${stunden(auftrag.geschaetzte_arbeitsstunden)} – leer lassen, um nur die Kosten zu ändern`}>
          <input type="number" min="0" step="0.25" value={werte.geschaetzte_arbeitsstunden} onChange={setze('geschaetzte_arbeitsstunden')} />
        </Feld>
        <Feld label="Kosten in Euro" fehler={felder.geschaetzte_kosten}
              hinweis={`Aktuell ${euro(auftrag.geschaetzte_kosten)} – leer lassen, um nur die Stunden zu ändern`}>
          <input type="number" min="0" step="0.01" value={werte.geschaetzte_kosten} onChange={setze('geschaetzte_kosten')} />
        </Feld>
      </div>
      <Feld label="Begründung" fehler={felder.grund} hinweis="Pflichtangabe, wird im Protokoll gespeichert">
        <textarea rows={2} value={werte.grund} onChange={setze('grund')} required />
      </Feld>
      <p className="leise">Die bisherigen Schätzungen bleiben im Protokoll erhalten.</p>
    </FokusFormular>
  )
}

// Termin = Zusage an den Kunden: nur Werkstattleitung/Admin (4.2, 7.2)
function TerminFormular({ formular, auftrag, onGespeichert }) {
  const eingang = auftrag.erstellt_am.slice(0, 10)
  const [werte, setWerte] = useState({ geschaetztes_fertigstellungsdatum: auftrag.geschaetztes_fertigstellungsdatum ?? '', grund: '' })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const termin = werte.geschaetztes_fertigstellungsdatum
    vorabPruefen({
      geschaetztes_fertigstellungsdatum: (!termin && 'Bitte ein Datum wählen')
        || (termin === auftrag.geschaetztes_fertigstellungsdatum && 'Das ist der bisherige Termin')
        || (termin < eingang && 'Der Termin kann nicht vor dem Auftragseingang liegen'),
      grund: !werte.grund.trim() && 'Pflichtangabe, wird im Protokoll gespeichert',
    })
    return api.terminKorrigieren(auftrag.id, { geschaetztes_fertigstellungsdatum: termin, grund: werte.grund })
  }, onGespeichert)
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  return (
    <FokusFormular formular={formular} titel="Termin korrigieren" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText="Termin speichern">
      <div className="spalten spalten--eng">
        <Feld label="Voraussichtlich fertig am" fehler={felder.geschaetztes_fertigstellungsdatum}
              hinweis={`Bisher: ${datum(auftrag.geschaetztes_fertigstellungsdatum)}`}>
          <input type="date" min={eingang} value={werte.geschaetztes_fertigstellungsdatum}
                 onChange={setze('geschaetztes_fertigstellungsdatum')} required />
        </Feld>
      </div>
      <Feld label="Begründung" fehler={felder.grund} hinweis="Pflichtangabe, wird im Protokoll gespeichert">
        <textarea rows={2} value={werte.grund} onChange={setze('grund')} required />
      </Feld>
      <p className="leise">
        Der festgelegte Termin gilt, bis er automatisch neu berechnet wird – das passiert bei einer Umzuweisung
        oder Prioritätsänderung. Danach bei Bedarf erneut korrigieren.
      </p>
    </FokusFormular>
  )
}

function ZuweisungFormular({ formular, auftrag, mitarbeiter, onGespeichert }) {
  const [werte, setWerte] = useState({
    zugewiesener_mitarbeiter_id: auftrag.zugewiesener_mitarbeiter_id ?? '',
    prioritaet: auftrag.prioritaet,
  })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(
    () => api.auftragAendern(auftrag.id, {
      zugewiesener_mitarbeiter_id: werte.zugewiesener_mitarbeiter_id || null,
      prioritaet: werte.prioritaet,
    }),
    onGespeichert,
  )
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }
  // Ein inzwischen deaktivierter Mitarbeiter bleibt sichtbar, solange er zugewiesen ist
  const bisherFehlt = auftrag.zugewiesener_mitarbeiter_id && !mitarbeiter.some((m) => m.id === auftrag.zugewiesener_mitarbeiter_id)

  return (
    <FokusFormular formular={formular} titel="Zuweisung & Priorität" onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}>
      <div className="spalten spalten--eng">
        <Feld label="Zugewiesen an" fehler={felder.zugewiesener_mitarbeiter_id}>
          <select value={werte.zugewiesener_mitarbeiter_id} onChange={setze('zugewiesener_mitarbeiter_id')}>
            <option value="">Noch niemand</option>
            {bisherFehlt && (
              <option value={auftrag.zugewiesener_mitarbeiter_id}>{auftrag.zugewiesener_mitarbeiter_name} (deaktiviert)</option>
            )}
            {mitarbeiter.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Feld>
        <Feld label="Priorität" fehler={felder.prioritaet}>
          <select value={werte.prioritaet} onChange={setze('prioritaet')}>
            <option value="normal">Normal</option>
            <option value="hoch">Hoch</option>
          </select>
        </Feld>
      </div>
      <p className="leise">Der voraussichtliche Termin wird beim Speichern neu berechnet.</p>
    </FokusFormular>
  )
}

// --- Zugeklappte Lese-Bereiche -------------------------------------------------------

function Statusverlauf({ verlauf }) {
  const letzter = verlauf[verlauf.length - 1]
  const zusammenfassung = letzter
    && `${anzahl(verlauf.length, 'Eintrag', 'Einträge')}, zuletzt „${letzter.status.bezeichnung}“ am ${datum(letzter.geaendert_am)} von ${von(letzter.geaendert_von_name)}`
  return (
    <Aufklappbereich titel="Statusverlauf" zusammenfassung={zusammenfassung}>
      <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead><tr><th>Zeitpunkt</th><th>Status</th><th>Von</th><th>Kommentar</th></tr></thead>
          <tbody>
            {[...verlauf].reverse().map((v, i) => (
              <tr key={i}>
                <td>{zeit(v.geaendert_am)}</td>
                <td><Status status={v.status} /></td>
                <td>{von(v.geaendert_von_name)}</td>
                <td>{v.kommentar ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Aufklappbereich>
  )
}

function Unterbrechungen({ unterbrechungen }) {
  if (unterbrechungen.length === 0) return null
  const laufend = unterbrechungen.find((u) => !u.bis_datum)
  const zusammenfassung = laufend
    ? `${anzahl(unterbrechungen.length, 'Unterbrechung', 'Unterbrechungen')}, aktuell „${laufend.grund}“ seit ${datum(laufend.von_datum)}`
    : `${anzahl(unterbrechungen.length, 'Unterbrechung', 'Unterbrechungen')}, keine laufende`
  return (
    <Aufklappbereich titel="Unterbrechungen" zusammenfassung={zusammenfassung}>
      <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead><tr><th>Grund</th><th>Von</th><th>Bis</th></tr></thead>
          <tbody>
            {[...unterbrechungen].reverse().map((u) => (
              <tr key={u.id}>
                <td>{u.grund}</td>
                <td>{zeit(u.von_datum)}</td>
                <td>{u.bis_datum ? zeit(u.bis_datum) : <span className="leise">läuft noch</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Aufklappbereich>
  )
}

function Schaetzungen({ schaetzungen }) {
  const letzte = schaetzungen[schaetzungen.length - 1]
  const zusammenfassung = letzte
    ? `${anzahl(schaetzungen.length, 'Eintrag', 'Einträge')}, zuletzt ${letzte.methode === 'manuelle_korrektur' ? `Korrektur von ${von(letzte.korrigiert_von_name)}` : 'automatisch'} am ${datum(letzte.berechnet_am)}`
    : 'Noch keine Schätzung'
  return (
    <Aufklappbereich titel="Schätzungen" zusammenfassung={zusammenfassung}>
      <div className="tabelle-rahmen">
        <table className="tabelle">
          <thead>
            <tr><th>Zeitpunkt</th><th>Art</th><th className="zahl">Stunden</th><th className="zahl">Kosten</th><th>Termin</th><th>Grundlage</th></tr>
          </thead>
          <tbody>
            {[...schaetzungen].reverse().map((s) => (
              <tr key={s.id}>
                <td>{zeit(s.berechnet_am)}</td>
                <td>{METHODEN[s.methode] ?? s.methode}</td>
                <td className="zahl">{stunden(s.geschaetzte_stunden)}</td>
                <td className="zahl">{euro(s.geschaetzte_kosten)}</td>
                <td>{datum(s.geschaetztes_datum)}</td>
                <td>
                  {quelleText(s)}
                  {s.methode === 'manuelle_korrektur' && <>{von(s.korrigiert_von_name)}: „{s.grund}“</>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Aufklappbereich>
  )
}

// --- Seite ---------------------------------------------------------------------------

export default function AuftragDetail() {
  const { id } = useParams()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [auftrag, setAuftrag] = useState(null)
  const [alleStatus, setAlleStatus] = useState([])
  const [mitarbeiter, setMitarbeiter] = useState([])
  const [fehler, setFehler] = useState(null)

  const laden = useCallback(() => {
    api.auftrag(id).then(setAuftrag).catch((e) => setFehler(e.message))
  }, [id])

  useEffect(() => {
    laden()
    api.auftragsstatus().then(setAlleStatus).catch((e) => setFehler(e.message))
    api.mitarbeiter().then(setMitarbeiter).catch(() => {}) // nur für die Auswahl „Zugewiesen an“
  }, [laden])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!auftrag) return <p className="leise">Lädt …</p>

  const a = auftrag
  // Berechtigungsmatrix 7.2 – das Backend prüft dasselbe (darf_auftrag_bearbeiten, Werkstattleitung)
  const leitung = hatRolle('werkstattleiter')
  const darfBearbeiten = leitung || a.zugewiesener_mitarbeiter_id === angemeldeterNutzer()?.id

  function gespeichert(neu, text) {
    formular.gespeichert()
    setAuftrag(neu)
    rueckmeldung(text)
    hervorheben('eckdaten')
  }

  return (
    <>
      <nav className="brotkrumen"><span><Link to="/auftraege">Aufträge</Link></span><span>{a.auftragsnummer}</span></nav>
      <div className="kopf">
        <h1>Auftrag {a.auftragsnummer}</h1>
        <Status status={a.status} />
        {a.ist_ueberfaellig && <Ueberfaellig />}
        {a.prioritaet === 'hoch' && <HohePrioritaet />}
      </div>

      <dl className={`eckdaten${hervorgehoben === 'eckdaten' ? ' hervorgehoben' : ''}`}>
        <dt>Kunde</dt><dd><Link to={`/kunden/${a.kunde_id}`}>{a.kunde_name}</Link></dd>
        <dt>Instrument</dt><dd>{a.instrumentenklasse_bezeichnung}</dd>
        <dt>Reparatur</dt><dd>{a.reparaturart_bezeichnung} (Komplexität {a.komplexitaet})</dd>
        <dt>Zugewiesen an</dt><dd>{a.zugewiesener_mitarbeiter_name ?? <span className="leise">nicht zugewiesen</span>}</dd>
        <dt>Priorität</dt><dd>{a.prioritaet === 'hoch' ? 'hoch' : 'normal'}</dd>
        <dt>Geschätzt</dt><dd>{stunden(a.geschaetzte_arbeitsstunden)} · {euro(a.geschaetzte_kosten)}</dd>
        <dt>Voraussichtlich fertig</dt>
        <dd>
          {datum(a.geschaetztes_fertigstellungsdatum)}
          {a.geschaetzte_bandbreite_von && (
            <span className="leise"> (zwischen {datum(a.geschaetzte_bandbreite_von)} und {datum(a.geschaetzte_bandbreite_bis)})</span>
          )}
        </dd>
        <dt>Eingang</dt><dd>{zeit(a.erstellt_am)}</dd>
        {a.tatsaechliches_fertigstellungsdatum && <><dt>Fertiggestellt am</dt><dd>{datum(a.tatsaechliches_fertigstellungsdatum)}</dd></>}
        <dt>Zugangscode Kunde</dt><dd><code>{a.zugriffstoken}</code></dd>
        {a.notizen && <><dt>Notizen</dt><dd>{a.notizen}</dd></>}
      </dl>

      {(darfBearbeiten || leitung) && (
        <div className="aktionsleiste">
          {darfBearbeiten && <AktionsButton formular={formular} schluessel={STATUS} primaer>Status ändern</AktionsButton>}
          {darfBearbeiten && <AktionsButton formular={formular} schluessel={KORREKTUR}>Schätzung korrigieren</AktionsButton>}
          {leitung && <AktionsButton formular={formular} schluessel={TERMIN}>Termin korrigieren</AktionsButton>}
          {leitung && <AktionsButton formular={formular} schluessel={ZUWEISUNG}>Zuweisung & Priorität</AktionsButton>}
        </div>
      )}
      {!darfBearbeiten && (
        <p className="leise">
          Status und Schätzung kann nur der zugewiesene Mitarbeiter oder die Werkstattleitung ändern,
          den Termin nur die Werkstattleitung.
        </p>
      )}

      <FormularBereich formular={formular}>
        {formular.offen === STATUS && (
          <StatusFormular key={STATUS} formular={formular} auftrag={a} alleStatus={alleStatus}
                          onGespeichert={(neu) => gespeichert(neu, `Status geändert: ${neu.status.bezeichnung}`)} />
        )}
        {formular.offen === KORREKTUR && (
          <KorrekturFormular key={KORREKTUR} formular={formular} auftrag={a}
                             onGespeichert={(neu) => gespeichert(neu,
                               `Schätzung korrigiert: ${stunden(neu.geschaetzte_arbeitsstunden)} · ${euro(neu.geschaetzte_kosten)}`)} />
        )}
        {formular.offen === TERMIN && (
          <TerminFormular key={TERMIN} formular={formular} auftrag={a}
                          onGespeichert={(neu) => gespeichert(neu,
                            `Termin korrigiert: voraussichtlich fertig am ${datum(neu.geschaetztes_fertigstellungsdatum)}`)} />
        )}
        {formular.offen === ZUWEISUNG && (
          <ZuweisungFormular key={ZUWEISUNG} formular={formular} auftrag={a} mitarbeiter={mitarbeiter}
                             onGespeichert={(neu) => gespeichert(neu,
                               `Gespeichert – voraussichtlich fertig: ${datum(neu.geschaetztes_fertigstellungsdatum)}`)} />
        )}
      </FormularBereich>

      <Statusverlauf verlauf={a.statusverlauf} />
      <Unterbrechungen unterbrechungen={a.unterbrechungen} />
      <Schaetzungen schaetzungen={a.schaetzungen} />
    </>
  )
}
