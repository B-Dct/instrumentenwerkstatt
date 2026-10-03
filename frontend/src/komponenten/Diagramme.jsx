// Einfache, selbst gezeichnete Diagramme für die Auswertungen (9.14) – ohne Diagramm-Bibliothek,
// Farben und Schrift aus dem Design-System (9.6). Jedes Diagramm hat eine Textalternative:
// Die Zahlen stehen zusätzlich als (unsichtbare) Tabelle bzw. direkt neben den Balken.

const MONATE = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const MONATE_LANG = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

// Obergrenze der Achse: nächste "runde" Zahl über dem größten Wert (1, 2, 5 × 10ⁿ, mindestens 4 Teilstriche sinnvoll)
function achsenMaximum(groesster) {
  if (groesster <= 0) return 4
  const zehner = 10 ** Math.floor(Math.log10(groesster))
  const stufe = [1, 2, 4, 5, 10].find((s) => s * zehner >= groesster)
  return Math.max(4, stufe * zehner)
}

// Liniendiagramm über die 12 Monate eines Jahres. werte: 12 Zahlen; null = kein Wert (z. B. Monat liegt noch in der Zukunft)
export function Monatsverlauf({ titel, werte, format = (w) => String(w), einheit = '' }) {
  const B = 640, H = 240, links = 44, rechts = 12, oben = 12, unten = 28
  const max = achsenMaximum(Math.max(0, ...werte.filter((w) => w !== null)))
  const x = (i) => links + (i * (B - links - rechts)) / 11
  const y = (w) => oben + (1 - w / max) * (H - oben - unten)
  const striche = [0, 1, 2, 3, 4].map((n) => (max * n) / 4)
  // Lücken (null) unterbrechen die Linie
  const abschnitte = werte.reduce((teile, w, i) => {
    if (w === null) return [...teile, []]
    teile[teile.length - 1].push(`${x(i)},${y(w)}`)
    return teile
  }, [[]]).filter((t) => t.length > 0)

  return (
    <figure className="diagramm">
      <figcaption>{titel}</figcaption>
      <svg viewBox={`0 0 ${B} ${H}`} role="img" aria-label={`${titel}: Liniendiagramm, Werte in der folgenden Tabelle`}>
        {striche.map((s) => (
          <g key={s}>
            <line className="diagramm__gitter" x1={links} x2={B - rechts} y1={y(s)} y2={y(s)} />
            <text className="diagramm__achse" x={links - 8} y={y(s)} textAnchor="end" dominantBaseline="middle">{format(s)}</text>
          </g>
        ))}
        {MONATE.map((m, i) => (
          <text key={m} className="diagramm__achse" x={x(i)} y={H - 8} textAnchor="middle">{m}</text>
        ))}
        {abschnitte.map((punkte) => <polyline key={punkte[0]} className="diagramm__linie" points={punkte.join(' ')} />)}
        {werte.map((w, i) => w !== null && (
          <circle key={MONATE[i]} className="diagramm__punkt" cx={x(i)} cy={y(w)} r="4">
            <title>{MONATE_LANG[i]}: {format(w)}{einheit}</title>
          </circle>
        ))}
      </svg>
      <table className="unsichtbar">
        <caption>{titel}</caption>
        <thead><tr><th>Monat</th><th>Wert</th></tr></thead>
        <tbody>
          {werte.map((w, i) => <tr key={MONATE[i]}><td>{MONATE_LANG[i]}</td><td>{w === null ? 'noch kein Wert' : `${format(w)}${einheit}`}</td></tr>)}
        </tbody>
      </table>
    </figure>
  )
}

// Waagerechte Balken für eine Verteilung. eintraege: [{ bezeichnung, anzahl, sonstige }]
export function Balkenverteilung({ titel, eintraege, leerText }) {
  const summe = eintraege.reduce((s, e) => s + e.anzahl, 0)
  const groesster = Math.max(1, ...eintraege.map((e) => e.anzahl))
  return (
    <figure className="diagramm">
      <figcaption>{titel}</figcaption>
      {eintraege.length === 0 ? <p className="leise">{leerText}</p> : (
        <ul className="balken">
          {eintraege.map((e) => (
            <li key={e.bezeichnung} className={e.sonstige ? 'balken__zeile balken__zeile--sonstige' : 'balken__zeile'}>
              <span className="balken__name">{e.bezeichnung}</span>
              <span className="balken__spur" aria-hidden="true"><span style={{ width: `${(e.anzahl / groesster) * 100}%` }} /></span>
              <span className="balken__wert">{e.anzahl} <span className="leise">({Math.round((e.anzahl / summe) * 100)} %)</span></span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
