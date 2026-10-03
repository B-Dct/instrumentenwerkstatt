// Einfache, selbst gezeichnete Diagramme für die Auswertungen (9.14) – ohne Diagramm-Bibliothek,
// Farben und Schrift aus dem Design-System (9.6). Jedes Diagramm hat eine Textalternative:
// Die Zahlen stehen zusätzlich als (unsichtbare) Tabelle bzw. direkt neben den Balken.
import { useEffect, useRef, useState } from 'react'

const MONATE = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const MONATE_LANG = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

const TEILSTRICHE = 4

// Abstand der Teilstriche: der kleinste "glatte" Schritt (1, 2, 2,5, 5 × 10ⁿ), mit dem vier Schritte
// den größten Wert erreichen – so stehen an der Achse nur runde Zahlen. Bei Anzahlen mindestens 1.
function achsenSchritt(groesster, ganzzahlig) {
  const mindestens = ganzzahlig ? 1 : 0
  if (groesster <= 0) return Math.max(mindestens, 1)
  const zehner = 10 ** Math.floor(Math.log10(groesster / TEILSTRICHE))
  const schritt = [1, 2, 2.5, 5, 10].map((s) => s * zehner).find((s) => s * TEILSTRICHE >= groesster)
  return Math.max(mindestens, schritt)
}

// Liniendiagramm über die 12 Monate eines Jahres. werte: 12 Zahlen; null = kein Wert (z. B. Monat liegt noch in der Zukunft)
// Breite des umgebenden Elements in Pixeln – das Diagramm wird in echter Größe gezeichnet statt
// hochskaliert, damit Schrift, Linien und Punkte so fein bleiben wie im Rest der Seite
function useBreite(standard) {
  const ref = useRef(null)
  const [breite, setBreite] = useState(standard)
  useEffect(() => {
    const beobachter = new ResizeObserver(([eintrag]) => setBreite(Math.round(eintrag.contentRect.width)))
    beobachter.observe(ref.current)
    return () => beobachter.disconnect()
  }, [])
  return [ref, breite]
}

// ganzzahlig: für Anzahlen (keine halben Teilstriche)
// format: kurze Zahl über dem Punkt; genau: ausführlicher Wert beim Zeigen und in der Tabelle (Standard: wie format)
export function Monatsverlauf({ titel, werte, format = (w) => String(w), genau = format, einheit = '', ganzzahlig = false }) {
  const [ref, B] = useBreite(640)
  const H = 210, rechts = 20, oben = 24, unten = 24  // oben Platz für die Zahl über dem höchsten Punkt
  const schritt = achsenSchritt(Math.max(0, ...werte.filter((w) => w !== null)), ganzzahlig)
  const max = schritt * TEILSTRICHE
  // Achsenbeschriftung ohne unnötige Nachkommastellen (die Teilstriche sind glatte Werte)
  const achse = (w) => w.toLocaleString('de-DE', { maximumFractionDigits: 2 })
  // Platz links je nach Länge der längsten Beschriftung (z. B. „2.000“ braucht mehr als „4“)
  const links = Math.max(32, achse(max).length * 7 + 14)
  const x = (i) => links + (i * (B - links - rechts)) / 11
  const y = (w) => oben + (1 - w / max) * (H - oben - unten)
  const striche = Array.from({ length: TEILSTRICHE + 1 }, (_, n) => schritt * n)
  // Lücken (null) unterbrechen die Linie
  const abschnitte = werte.reduce((teile, w, i) => {
    if (w === null) return [...teile, []]
    teile[teile.length - 1].push(`${x(i)},${y(w)}`)
    return teile
  }, [[]]).filter((t) => t.length > 0)

  return (
    <figure className="diagramm" ref={ref}>
      <figcaption>{titel}</figcaption>
      <svg width={B} height={H} viewBox={`0 0 ${B} ${H}`} role="img" aria-label={`${titel}: Liniendiagramm, Werte in der folgenden Tabelle`}>
        {striche.map((s) => (
          <g key={s}>
            <line className="diagramm__gitter" x1={links} x2={B - rechts} y1={y(s)} y2={y(s)} />
            <text className="diagramm__achse" x={links - 8} y={y(s)} textAnchor="end" dominantBaseline="middle">{achse(s)}</text>
          </g>
        ))}
        {MONATE.map((m, i) => (
          <text key={m} className="diagramm__achse" x={x(i)} y={H - 6} textAnchor="middle">{m}</text>
        ))}
        {abschnitte.map((punkte) => <polyline key={punkte[0]} className="diagramm__linie" points={punkte.join(' ')} />)}
        {/* Der Wert steht als Zahl über jedem Punkt */}
        {werte.map((w, i) => w !== null && (
          <text key={MONATE[i]} className="diagramm__wert" x={x(i)} y={y(w) - 8} textAnchor="middle" aria-hidden="true">{format(w)}</text>
        ))}
        {werte.map((w, i) => w !== null && (
          <circle key={MONATE[i]} className="diagramm__punkt" cx={x(i)} cy={y(w)} r="3">
            <title>{MONATE_LANG[i]}: {genau(w)}{einheit}</title>
          </circle>
        ))}
      </svg>
      <table className="unsichtbar">
        <caption>{titel}</caption>
        <thead><tr><th>Monat</th><th>Wert</th></tr></thead>
        <tbody>
          {werte.map((w, i) => <tr key={MONATE[i]}><td>{MONATE_LANG[i]}</td><td>{w === null ? 'noch kein Wert' : `${genau(w)}${einheit}`}</td></tr>)}
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
