// Reparaturarten mit Standard-Komplexität pflegen (2.6) – nur Admin (7.2)
import { api } from '../../api.js'
import { Feld } from '../../komponenten/FokusFormular.jsx'
import StammdatenListe from './StammdatenListe.jsx'

const TEXT = {
  titel: 'Reparaturarten',
  einzahl: 'Reparaturart',
  neu: 'Neue Reparaturart',
  leer: 'Noch keine Reparaturarten angelegt.',
  beschreibung: 'Die Standard-Komplexität wird bei neuen Aufträgen vorbelegt und kann dort überschrieben werden. '
    + 'Archivierte Reparaturarten stehen für neue Aufträge nicht mehr zur Auswahl.',
}

const SPALTEN = [
  { titel: 'Bezeichnung', spalte: 'bezeichnung', wert: (e) => e.bezeichnung },
  { titel: 'Standard-Komplexität', spalte: 'standard_komplexitaet', wert: (e) => `${e.standard_komplexitaet} von 5` },
]

export function ArtFelder({ werte, setze, felder }) {
  return (
    <div className="spalten spalten--eng">
      <Feld label="Bezeichnung" fehler={felder.bezeichnung} hinweis="z. B. Saitenwechsel, Ventil-Überholung">
        <input value={werte.bezeichnung} onChange={setze('bezeichnung')} required maxLength={150} autoComplete="off" />
      </Feld>
      <Feld label="Standard-Komplexität" fehler={felder.standard_komplexitaet} hinweis="1 = einfach, 5 = sehr aufwendig">
        <select value={werte.standard_komplexitaet} onChange={setze('standard_komplexitaet')} required>
          {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </Feld>
    </div>
  )
}

export default function Reparaturarten() {
  return (
    <StammdatenListe
      text={TEXT}
      laden={api.admin.arten}
      anlegen={api.admin.artAnlegen}
      aendern={api.admin.artAendern}
      archivieren={api.admin.artArchivieren}
      reaktivieren={api.admin.artReaktivieren}
      spalten={SPALTEN}
      sortierung="bezeichnung"
      suchhinweis="Suchen: Bezeichnung"
      startwerte={(e) => ({ bezeichnung: e?.bezeichnung ?? '', standard_komplexitaet: String(e?.standard_komplexitaet ?? 2) })}
      zuDaten={(w) => ({ bezeichnung: w.bezeichnung, standard_komplexitaet: Number(w.standard_komplexitaet) })}
      Felder={ArtFelder}
    />
  )
}
