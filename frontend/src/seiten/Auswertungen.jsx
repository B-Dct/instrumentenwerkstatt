// Auswertungen / Jahresstatistik (9.14) – nur Werkstattleitung und Admin (7.2).
// Die Übersicht zeigt den Stand heute, diese Seite die Entwicklung über das gewählte Jahr.
// Grundlage sind die im Jahr abgeschlossenen Aufträge (Fertigstellungsdatum im Jahr).
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { api, euro, zahl } from '../api.js'
import { Balkenverteilung, Monatsverlauf } from '../komponenten/Diagramme.jsx'

// Monate, die im laufenden Jahr noch in der Zukunft liegen, zeigen keinen Wert statt einer irreführenden 0
function ohneZukunft(werte, jahr) {
  const heute = new Date()
  return jahr < heute.getFullYear() ? werte : werte.map((w, i) => (i > heute.getMonth() ? null : w))
}

// wert = null: es gibt im gewählten Jahr keine Grundlage für diese Kennzahl
function Kennzahl({ wert, titel, zusatz }) {
  return (
    <li>
      <div className="kachel">
        <span className="kachel__zahl">{wert ?? '–'}</span>
        <span className="kachel__titel">{titel}</span>
        {zusatz && <small className="leise">{zusatz}</small>}
      </div>
    </li>
  )
}

const eineStelle = (w) => w.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const auftraege = (n) => `${n} ${n === 1 ? 'Auftrag' : 'Aufträge'}`

function Menge({ menge, jahr }) {
  const leer = `Im Jahr ${jahr} wurde noch kein Auftrag abgeschlossen.`
  return (
    <section className="abschnitt">
      <h2>Menge</h2>
      <ul className="kacheln" aria-label="Kennzahlen Menge">
        <Kennzahl wert={menge.abgeschlossen} titel={`Abgeschlossene Aufträge ${jahr}`} />
      </ul>
      <Monatsverlauf titel="Abgeschlossene Aufträge pro Monat" werte={ohneZukunft(menge.pro_monat, jahr)} ganzzahlig />
      <div className="spalten">
        <Balkenverteilung titel="Nach Reparaturart" eintraege={menge.nach_reparaturart} leerText={leer} />
        <Balkenverteilung titel="Nach Instrumentenklasse" eintraege={menge.nach_instrumentenklasse} leerText={leer} />
      </div>
    </section>
  )
}

function Zeit({ zeit, abgeschlossen }) {
  const ohneZeiterfassung = abgeschlossen - zeit.auftraege_mit_zeiterfassung
  const ohnePrognose = abgeschlossen - zeit.auftraege_mit_terminprognose
  return (
    <section className="abschnitt">
      <h2>Zeit</h2>
      <ul className="kacheln" aria-label="Kennzahlen Zeit">
        <Kennzahl wert={zeit.bearbeitungsdauer_tage === null ? null : `${eineStelle(zeit.bearbeitungsdauer_tage)} Tage`}
                  titel="Ø Bearbeitungsdauer" zusatz="Kalendertage vom Eingang bis zur Fertigstellung, inklusive Wartezeiten" />
        <Kennzahl wert={zeit.arbeitszeit_stunden === null ? null : `${zahl(zeit.arbeitszeit_stunden)} Std.`}
                  titel="Ø reine Arbeitszeit"
                  zusatz={`Erfasste Arbeitszeit je Auftrag, ohne Wartezeiten${ohneZeiterfassung > 0 ? ` · ${auftraege(ohneZeiterfassung)} ohne Zeiterfassung nicht eingerechnet` : ''}`} />
        <Kennzahl wert={zeit.puenktlichkeit_prozent === null ? null : `${zeit.puenktlichkeit_prozent} %`}
                  titel="Pünktlichkeitsquote"
                  zusatz={zeit.auftraege_mit_terminprognose === 0
                    ? 'Gemessen an der ersten automatischen Terminschätzung – dafür gibt es in diesem Jahr noch keine Grundlage'
                    : `${zeit.puenktlich} von ${zeit.auftraege_mit_terminprognose} nicht später fertig als die erste automatische Terminschätzung (spätere Korrekturen zählen nicht)${ohnePrognose > 0 ? ` · ${auftraege(ohnePrognose)} ohne Terminschätzung nicht eingerechnet` : ''}`} />
      </ul>
      <Monatsverlauf titel="Ø Bearbeitungsdauer pro Monat (Kalendertage, nach Monat der Fertigstellung)"
                     werte={zeit.bearbeitungsdauer_pro_monat} format={eineStelle} einheit=" Tage" />
    </section>
  )
}

const ganzeEuro = (w) => `${w.toLocaleString('de-DE', { maximumFractionDigits: 0 })} €`

function Geld({ geld, abgeschlossen, jahr }) {
  const ohneKosten = abgeschlossen - geld.auftraege_mit_kosten
  const fehlend = ohneKosten > 0 ? ` · ${auftraege(ohneKosten)} ohne eingetragene Kosten nicht eingerechnet` : ''
  return (
    <section className="abschnitt">
      <h2>Geld</h2>
      <ul className="kacheln" aria-label="Kennzahlen Geld">
        <Kennzahl wert={geld.auftraege_mit_kosten === 0 ? null : euro(geld.umsatz)} titel={`Umsatz ${jahr}`}
                  zusatz={`Summe der tatsächlich abgerechneten Kosten der abgeschlossenen Aufträge${fehlend}`} />
        <Kennzahl wert={geld.auftragswert === null ? null : euro(geld.auftragswert)} titel="Ø Auftragswert"
                  zusatz={`Umsatz geteilt durch ${auftraege(geld.auftraege_mit_kosten)} mit eingetragenen Kosten`} />
      </ul>
      <Monatsverlauf titel="Umsatz pro Monat (nach Monat der Fertigstellung)"
                     werte={ohneZukunft(geld.umsatz_pro_monat, jahr)} format={ganzeEuro} genau={euro} />
    </section>
  )
}

// Tendenz in Worten: positiv = tatsächlich mehr als geschätzt
function tendenz(prozent, mehr, weniger) {
  if (prozent === 0) return 'im Schnitt weder zu hoch noch zu niedrig geschätzt'
  return prozent > 0 ? `tatsächlich im Schnitt ${prozent} % ${mehr} als geschätzt` : `tatsächlich im Schnitt ${-prozent} % ${weniger} als geschätzt`
}

function Schaetzgenauigkeit({ genau }) {
  const kachel = (a, titel, istWert, mehr, weniger) => (
    <Kennzahl wert={a.abweichung_prozent === null ? null : `${a.abweichung_prozent} %`} titel={titel}
              zusatz={a.auftraege === 0
                ? `Noch keine Grundlage: Es braucht abgeschlossene Aufträge mit automatischer Schätzung und ${istWert}`
                : `Aus ${auftraege(a.auftraege)} · ${tendenz(a.tendenz_prozent, mehr, weniger)}`} />
  )
  return (
    <section className="abschnitt">
      <h2>Schätzgenauigkeit</h2>
      <p className="leise seitenbeschreibung">
        Verglichen wird die erste automatische Schätzung beim Anlegen des Auftrags mit dem tatsächlichen Wert –
        spätere manuelle Korrekturen zählen bewusst nicht. So zeigt sich, wie gut die automatische Schätzung selbst ist.
      </p>
      <ul className="kacheln" aria-label="Kennzahlen Schätzgenauigkeit">
        {kachel(genau.stunden, 'Ø Abweichung Stunden', 'erfasster Arbeitszeit', 'mehr Stunden', 'weniger Stunden')}
        {kachel(genau.kosten, 'Ø Abweichung Kosten', 'abgerechnetem Betrag', 'teurer', 'günstiger')}
      </ul>
    </section>
  )
}

export default function Auswertungen() {
  const [adresse, setAdresse] = useSearchParams()
  const [daten, setDaten] = useState(null)
  const [fehler, setFehler] = useState(null)
  const gewaehlt = adresse.get('jahr')

  useEffect(() => {
    let abgebrochen = false
    api.auswertungen(gewaehlt ? { jahr: gewaehlt } : {})
      .then((d) => { if (!abgebrochen) { setDaten(d); setFehler(null) } })
      .catch((e) => { if (!abgebrochen) setFehler(e.message) })
    return () => { abgebrochen = true }
  }, [gewaehlt])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!daten) return <p className="leise">Lädt …</p>

  // Das laufende Jahr ist der Standard und steht nicht in der Adresse
  const jahrWaehlen = (jahr) => setAdresse(Number(jahr) === daten.jahre[0] ? {} : { jahr }, { replace: true })

  return (
    <>
      <div className="kopf">
        <h1>Auswertungen</h1>
        <label className="feld feld--inline kopf__aktion">
          <span>Jahr</span>
          <select value={daten.jahr} onChange={(e) => jahrWaehlen(e.target.value)}>
            {daten.jahre.map((j) => <option key={j} value={j}>{j}</option>)}
          </select>
        </label>
      </div>
      <p className="leise seitenbeschreibung">
        Gezählt werden die Aufträge, die im Jahr {daten.jahr} abgeschlossen wurden (Fertigstellungsdatum im Jahr,
        nicht der Auftragseingang).
      </p>

      <Menge menge={daten.menge} jahr={daten.jahr} />
      <Zeit zeit={daten.zeit} abgeschlossen={daten.menge.abgeschlossen} />
      <Geld geld={daten.geld} abgeschlossen={daten.menge.abgeschlossen} jahr={daten.jahr} />
      <Schaetzgenauigkeit genau={daten.schaetzgenauigkeit} />
    </>
  )
}
