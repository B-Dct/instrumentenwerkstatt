// Formulare für Kunde und Instrument – eingebettet über FokusFormular (9.10).
import { useState } from 'react'
import { api } from '../api.js'
import { Feld, FokusFormular } from '../komponenten/FokusFormular.jsx'
import { leerZuNull, useSpeichern } from '../komponenten/speichern.js'

// kunde = null → neuen Kunden anlegen
export function KundeFormular({ formular, kunde = null, onGespeichert }) {
  const [werte, setWerte] = useState({ name: kunde?.name ?? '', email: kunde?.email ?? '', telefon: kunde?.telefon ?? '' })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const daten = { name: werte.name, email: leerZuNull(werte.email), telefon: leerZuNull(werte.telefon) }
    return kunde ? api.kundeAendern(kunde.id, daten) : api.kundeAnlegen(daten)
  }, onGespeichert)
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  return (
    <FokusFormular formular={formular} titel={kunde ? 'Kunde bearbeiten' : 'Neuer Kunde'}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText={kunde ? 'Speichern' : 'Kunde anlegen'}>
      <Feld label="Name" fehler={felder.name}>
        <input value={werte.name} onChange={setze('name')} required maxLength={200} autoComplete="off" />
      </Feld>
      <div className="spalten spalten--eng">
        <Feld label="E-Mail" fehler={felder.email} hinweis="Optional, für Statusbenachrichtigungen">
          <input type="email" value={werte.email} onChange={setze('email')} autoComplete="off" />
        </Feld>
        <Feld label="Telefon" fehler={felder.telefon} hinweis="Optional">
          <input type="tel" value={werte.telefon} onChange={setze('telefon')} maxLength={50} autoComplete="off" />
        </Feld>
      </div>
      {!kunde && <p className="leise">Die Kundennummer wird automatisch vergeben.</p>}
    </FokusFormular>
  )
}

// instrument = null → neues Instrument für kundeId anlegen
export function InstrumentFormular({ formular, kundeId, instrument = null, klassen, onGespeichert, zusatz }) {
  const [werte, setWerte] = useState({
    instrumentenklasse_id: instrument?.instrumentenklasse_id ?? '',
    hersteller: instrument?.hersteller ?? '',
    typenbezeichnung: instrument?.typenbezeichnung ?? '',
    baujahr: instrument?.baujahr ?? '',
    seriennummer: instrument?.seriennummer ?? '',
    notizen: instrument?.notizen ?? '',
  })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const daten = {
      instrumentenklasse_id: werte.instrumentenklasse_id || null,
      hersteller: leerZuNull(werte.hersteller),
      typenbezeichnung: leerZuNull(werte.typenbezeichnung),
      baujahr: werte.baujahr === '' ? null : Number(werte.baujahr),
      seriennummer: leerZuNull(werte.seriennummer),
      notizen: leerZuNull(werte.notizen),
    }
    return instrument ? api.instrumentAendern(instrument.id, daten) : api.instrumentAnlegen({ ...daten, kunde_id: kundeId })
  }, onGespeichert)
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  // Eine inzwischen archivierte Klasse des bestehenden Instruments trotzdem anzeigen
  const klassenAuswahl = instrument && !klassen.some((k) => k.id === instrument.instrumentenklasse_id)
    ? [...klassen, { id: instrument.instrumentenklasse_id, bezeichnung: `${instrument.instrumentenklasse_bezeichnung} (archiviert)` }]
    : klassen

  return (
    <FokusFormular formular={formular} titel={instrument ? 'Instrument bearbeiten' : 'Instrument hinzufügen'}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler} zusatz={zusatz}
                   speichernText={instrument ? 'Speichern' : 'Instrument hinzufügen'}>
      <Feld label="Instrumentenklasse" fehler={felder.instrumentenklasse_id}>
        <select value={werte.instrumentenklasse_id} onChange={setze('instrumentenklasse_id')} required>
          <option value="">Bitte wählen</option>
          {klassenAuswahl.map((k) => <option key={k.id} value={k.id}>{k.bezeichnung}</option>)}
        </select>
      </Feld>
      <div className="spalten spalten--eng">
        <Feld label="Hersteller" fehler={felder.hersteller}>
          <input value={werte.hersteller} onChange={setze('hersteller')} maxLength={150} autoComplete="off" />
        </Feld>
        <Feld label="Typ / Modell" fehler={felder.typenbezeichnung}>
          <input value={werte.typenbezeichnung} onChange={setze('typenbezeichnung')} maxLength={150} autoComplete="off" />
        </Feld>
        <Feld label="Baujahr" fehler={felder.baujahr} hinweis="Optional">
          <input type="number" min="1500" max="2100" value={werte.baujahr} onChange={setze('baujahr')} />
        </Feld>
        <Feld label="Seriennummer" fehler={felder.seriennummer} hinweis="Optional">
          <input value={werte.seriennummer} onChange={setze('seriennummer')} maxLength={100} autoComplete="off" />
        </Feld>
      </div>
      <Feld label="Notizen" fehler={felder.notizen} hinweis="z. B. Besonderheiten, bekannte Vorschäden">
        <textarea rows={2} value={werte.notizen} onChange={setze('notizen')} />
      </Feld>
    </FokusFormular>
  )
}
