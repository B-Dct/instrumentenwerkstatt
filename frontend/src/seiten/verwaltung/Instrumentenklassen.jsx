// Instrumentenklassen pflegen (2.4) – nur Admin (7.2)
import { api } from '../../api.js'
import { Feld } from '../../komponenten/FokusFormular.jsx'
import StammdatenListe from './StammdatenListe.jsx'

const TEXT = {
  titel: 'Instrumentenklassen',
  einzahl: 'Instrumentenklasse',
  neu: 'Neue Instrumentenklasse',
  leer: 'Noch keine Instrumentenklassen angelegt.',
  beschreibung: 'Archivierte Klassen stehen für neue Instrumente nicht mehr zur Auswahl, bestehende Instrumente behalten sie.',
}

const SPALTEN = [
  { titel: 'Bezeichnung', wert: (e) => e.bezeichnung },
  { titel: 'Oberkategorie', wert: (e) => e.oberkategorie },
]

function Felder({ werte, setze, felder }) {
  return (
    <div className="spalten spalten--eng">
      <Feld label="Bezeichnung" fehler={felder.bezeichnung} hinweis="z. B. Violine, Trompete">
        <input value={werte.bezeichnung} onChange={setze('bezeichnung')} required maxLength={100} autoComplete="off" />
      </Feld>
      <Feld label="Oberkategorie" fehler={felder.oberkategorie} hinweis="z. B. Streichinstrument">
        <input value={werte.oberkategorie} onChange={setze('oberkategorie')} required maxLength={100}
               list="oberkategorien" autoComplete="off" />
      </Feld>
      <datalist id="oberkategorien">
        {['Streichinstrument', 'Zupfinstrument', 'Holzblasinstrument', 'Blechblasinstrument', 'Tasteninstrument', 'Schlaginstrument']
          .map((k) => <option key={k} value={k} />)}
      </datalist>
    </div>
  )
}

export default function Instrumentenklassen() {
  return (
    <StammdatenListe
      text={TEXT}
      laden={api.admin.klassen}
      anlegen={api.admin.klasseAnlegen}
      aendern={api.admin.klasseAendern}
      archivieren={api.admin.klasseArchivieren}
      reaktivieren={api.admin.klasseReaktivieren}
      spalten={SPALTEN}
      startwerte={(e) => ({ bezeichnung: e?.bezeichnung ?? '', oberkategorie: e?.oberkategorie ?? '' })}
      zuDaten={(w) => ({ bezeichnung: w.bezeichnung, oberkategorie: w.oberkategorie })}
      Felder={Felder}
    />
  )
}
