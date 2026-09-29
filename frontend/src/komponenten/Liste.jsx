// Bausteine für Listen nach Datenmodell 9.11 (Zustand: liste.js)

// Suchfeld, Filter, aktive Filter als Chips, "Alle Filter zurücksetzen", Trefferzahl
export function Listenkopf({ liste, suchhinweis }) {
  const { daten, zustand, filter, aktiveFilter } = liste
  return (
    <div className="listenkopf">
      <div className="filterleiste">
        <label className="feld feld--inline">
          <span className="unsichtbar">Suche</span>
          <input type="search" placeholder={suchhinweis} value={liste.sucheEingabe}
                 onChange={(e) => liste.setSucheEingabe(e.target.value)} />
        </label>
        {filter.map((f) => (
          <label key={f.name} className="feld feld--inline">
            <span>{f.label}</span>
            <select value={zustand[f.name]} onChange={(e) => liste.setzeFilter(f.name, e.target.value)}>
              {f.optionen.map((o) => <option key={o.wert} value={o.wert}>{o.text}</option>)}
            </select>
          </label>
        ))}
      </div>
      <div className="filterchips" aria-live="polite">
        {daten && (
          <span className="trefferzahl">
            {/* "4 von 5", sobald nicht alles gezeigt wird – auch wenn nur ein Standardfilter greift */}
            {daten.treffer === daten.gesamt
              ? `${daten.gesamt} ${daten.gesamt === 1 ? 'Eintrag' : 'Einträge'}`
              : `${daten.treffer} von ${daten.gesamt} Einträgen`}
          </span>
        )}
        {zustand.suche && (
          <span className="chip">„{zustand.suche}“
            <button type="button" aria-label={`Suche „${zustand.suche}“ entfernen`} onClick={liste.entferneSuche}>×</button>
          </span>
        )}
        {aktiveFilter.map((f) => (
          <span key={f.name} className="chip">{f.label}: {f.text}
            <button type="button" aria-label={`Filter ${f.label} entfernen`}
                    onClick={() => liste.setzeFilter(f.name, f.standard ?? '')}>×</button>
          </span>
        ))}
        {liste.gefiltert && (
          <button type="button" className="link-button" onClick={liste.zuruecksetzen}>Alle Filter zurücksetzen</button>
        )}
      </div>
    </div>
  )
}

// Sortierbarer Spaltenkopf
export function SortierKopf({ liste, spalte, children, zahl = false }) {
  const aktiv = liste.zustand.sortierung === spalte
  const richtung = aktiv ? liste.zustand.richtung : null
  return (
    <th className={zahl ? 'zahl' : undefined}
        aria-sort={richtung === 'auf' ? 'ascending' : richtung === 'ab' ? 'descending' : 'none'}>
      <button type="button" className="sortierknopf" onClick={() => liste.sortiere(spalte)}>
        {children}
        <span aria-hidden="true" className="sortierzeichen">{richtung === 'auf' ? '▲' : richtung === 'ab' ? '▼' : '↕'}</span>
      </button>
    </th>
  )
}

// Seitenwahl unter der Liste (nur wenn es mehr als eine Seite gibt)
export function Seitenwahl({ liste }) {
  const { daten } = liste
  if (!daten) return null
  const seiten = Math.max(1, Math.ceil(daten.treffer / daten.seitengroesse))
  if (seiten <= 1) return null
  return (
    <nav className="seitenwahl" aria-label="Seiten">
      <button type="button" className="btn btn--sekundaer btn--klein" disabled={daten.seite <= 1}
              onClick={() => liste.zurSeite(daten.seite - 1)}>Zurück</button>
      <span>Seite {daten.seite} von {seiten}</span>
      <button type="button" className="btn btn--sekundaer btn--klein" disabled={daten.seite >= seiten}
              onClick={() => liste.zurSeite(daten.seite + 1)}>Weiter</button>
    </nav>
  )
}

// Leere Ergebnisse (9.11, Punkt 7)
export function ListeLeer({ liste, leerText }) {
  if (!liste.daten || liste.daten.eintraege.length > 0) return null
  if (liste.gefiltert) {
    return (
      <p className="leise">Keine Treffer.{' '}
        <button type="button" className="link-button" onClick={liste.zuruecksetzen}>Alle Filter zurücksetzen</button>
      </p>
    )
  }
  return <p className="leise">{leerText}</p>
}
