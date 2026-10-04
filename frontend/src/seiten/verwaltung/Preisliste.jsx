// Preisliste als Matrix (9.15) – nur Admin (7.2): Zeilen sind Instrumentenklassen (nach Oberkategorie
// gruppiert, einklappbar), Spalten sind Reparaturarten, in den Zellen stehen Richtpreis und Richtzeit (2.6a).
// Nur eine andere Darstellung derselben Daten wie die Liste (Vorgabewerte.jsx); gespeichert wird über
// dieselben Endpunkte. Wie das Abwesenheits-Raster (9.13) eine bewusste Ausnahme von Regel 9.10:
// Ein Klick auf eine Zelle öffnet den Editor direkt unter der Zeile.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { alleEintraege, api, euro, stunden } from '../../api.js'
import { AktionsButton, FokusFormular, FormularBereich, Rueckfrage } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { instrumenteHinweis, leerZuNull, useSpeichern } from '../../komponenten/speichern.js'
import { KlasseFelder } from './Instrumentenklassen.jsx'
import { ArtFelder } from './Reparaturarten.jsx'

const KLASSE_NEU = 'klasse-neu'
const ART_NEU = 'art-neu'
const ALLGEMEIN = 'allgemein' // Zeile für Werte, die für alle Instrumentenklassen gelten
const zellSchluessel = (klasseId, artId) => `zelle|${klasseId}|${artId}`
const istZelle = (schluessel) => typeof schluessel === 'string' && schluessel.startsWith('zelle|')

const enthaelt = (text, suche) => text.toLowerCase().includes(suche.trim().toLowerCase())
// Standardausführung zuerst, dann die Ausführungen alphabetisch
const nachAusfuehrung = (a, b) => (a.ausfuehrung ?? '').localeCompare(b.ausfuehrung ?? '', 'de')

// Richtzeit als Vorschlag aus Preis ÷ Stundensatz, auf 0,25 Std. gerundet (9.15)
function zeitVorschlag(preis, stundensatz) {
  if (!(Number(preis) > 0) || !(stundensatz > 0)) return null
  return Math.max(0.25, Math.round((Number(preis) / stundensatz) * 4) / 4)
}

function NeuFormular({ formular, titel, speichernText, Felder, startwerte, zuDaten, anlegen, onGespeichert }) {
  const [werte, setWerte] = useState(startwerte)
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(
    () => anlegen(zuDaten(werte)), onGespeichert, { konfliktFeld: 'bezeichnung' },
  )
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }
  return (
    <FokusFormular formular={formular} titel={titel} onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText={speichernText}>
      <Felder werte={werte} setze={setze} felder={felder} />
    </FokusFormular>
  )
}

let laufendeNummer = 0
const neueZeile = (wert) => ({
  schluessel: wert?.id ?? `neu-${laufendeNummer += 1}`,
  id: wert?.id ?? null,
  ausfuehrung: wert?.ausfuehrung ?? '',
  istStandard: wert?.ist_standard ?? false,
  instrumente: wert?.instrumente_mit_ausfuehrung ?? 0,
  preis: wert ? String(wert.vorgabe_kosten) : '',
  zeit: wert ? String(wert.vorgabe_stunden) : '',
  notiz: wert?.notiz ?? '',
  vorschlag: false, // Richtzeit wurde aus dem Preis vorgeschlagen und noch nicht selbst geändert
})
const zeileLeer = (z) => !z.id && !z.ausfuehrung.trim() && z.preis === '' && z.zeit === '' && !z.notiz.trim()
const zuDaten = (z) => ({
  ausfuehrung: leerZuNull(z.ausfuehrung.trim()),
  vorgabe_kosten: z.preis === '' ? null : Number(z.preis),
  vorgabe_stunden: z.zeit === '' ? null : Number(z.zeit),
  notiz: leerZuNull(z.notiz),
})
const gleich = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// Editor einer Zelle: je Ausführung eine Zeile mit Richtpreis, Richtzeit und Notiz
function ZellenEditor({ formular, klasse, art, werte, allgemein, stundensatz, onGeaendert, onFertig }) {
  const rueckmeldung = useRueckmeldung()
  const [zeilen, setZeilen] = useState(() => (werte.length ? [...werte].sort(nachAusfuehrung).map(neueZeile) : [neueZeile()]))
  // Stand in der Datenbank je Zeile, um nur Geändertes zu senden
  const gespeichert = useRef(Object.fromEntries(werte.map((w) => [w.id, zuDaten(neueZeile(w))])))
  const [sendet, setSendet] = useState(false)
  const [fehler, setFehler] = useState(null)
  const [zeilenfehler, setZeilenfehler] = useState({})
  const [archivFrage, setArchivFrage] = useState(null)
  const name = `${art.bezeichnung} (${klasse?.bezeichnung ?? 'allgemein'})`
  // Es gibt Ausführungen, aber keine Zeile für die Standardausführung (9.15)
  const gefuellt = zeilen.filter((z) => !zeileLeer(z))
  const ohneStandard = klasse && gefuellt.length > 1 && gefuellt.every((z) => z.id) && !gefuellt.some((z) => z.istStandard)

  const aendern = (schluessel, feld, wert) => {
    setZeilenfehler((f) => (f[schluessel]?.[feld] ? { ...f, [schluessel]: { ...f[schluessel], [feld]: undefined } } : f))
    setZeilen((alle) => alle.map((z) => (z.schluessel === schluessel
      ? { ...z, [feld]: wert, vorschlag: feld === 'zeit' ? false : z.vorschlag } : z)))
  }
  // Nur der Preis ist eingetragen → Richtzeit vorschlagen, bleibt änderbar
  const zeitVorschlagen = (schluessel) => setZeilen((alle) => alle.map((z) => {
    const vorschlag = z.schluessel === schluessel && z.zeit === '' ? zeitVorschlag(z.preis, stundensatz) : null
    return vorschlag ? { ...z, zeit: String(vorschlag), vorschlag: true } : z
  }))

  async function speichern() {
    setSendet(true); setFehler(null)
    const neueFehler = {}
    const stand = []
    let geaendert = false
    for (const z of zeilen) {
      if (zeileLeer(z)) continue
      const daten = zuDaten(z)
      if (z.id && gleich(daten, gespeichert.current[z.id])) { stand.push(z); continue }
      const pflicht = { vorgabe_kosten: daten.vorgabe_kosten === null && 'Pflichtfeld', vorgabe_stunden: daten.vorgabe_stunden === null && 'Pflichtfeld' }
      if (pflicht.vorgabe_kosten || pflicht.vorgabe_stunden) { neueFehler[z.schluessel] = pflicht; stand.push(z); continue }
      try {
        const antwort = z.id
          ? await api.admin.vorgabewertAendern(z.id, daten)
          : await api.admin.vorgabewertAnlegen({ ...daten, reparaturart_id: art.id, instrumentenklasse_id: klasse?.id ?? null })
        gespeichert.current[antwort.id] = daten
        stand.push({ ...z, id: antwort.id, vorschlag: false })
        geaendert = true
      } catch (err) {
        // "gibt es bereits" gehört an die Ausführung, alles ohne Feldbezug unter die Zeile
        neueFehler[z.schluessel] = err.status === 409 ? { ausfuehrung: err.message }
          : Object.keys(err.felder ?? {}).length ? err.felder : { allgemein: err.message }
        stand.push(z)
      }
    }
    if (geaendert) onGeaendert()
    if (Object.keys(neueFehler).length === 0) {
      rueckmeldung(geaendert ? `Richtpreis ${name} gespeichert` : `Keine Änderungen an ${name}`)
      onFertig()
      return
    }
    setZeilen(stand.length ? stand : [neueZeile()])
    setZeilenfehler(neueFehler)
    setFehler('Bitte die markierten Felder prüfen')
    setSendet(false)
  }

  async function archivieren(z, bestaetigt = false) {
    setFehler(null)
    setArchivFrage(null)
    // Vor dem Archivieren zeigen, wie viele Instrumente die Ausführung verwenden (2.5)
    if (!bestaetigt && z.instrumente > 0) { setArchivFrage(z.schluessel); return }
    try {
      await api.admin.vorgabewertArchivieren(z.id)
    } catch (err) {
      setFehler(err.message)
      return
    }
    rueckmeldung(`Richtpreis ${name}${z.ausfuehrung ? `, ${z.ausfuehrung}` : ''} archiviert – in der Listenansicht reaktivierbar`)
    onGeaendert()
    const rest = zeilen.filter((x) => x.schluessel !== z.schluessel)
    if (rest.some((x) => !zeileLeer(x))) setZeilen(rest)
    else onFertig()
  }

  const entfernen = (z) => setZeilen((alle) => {
    const rest = alle.filter((x) => x.schluessel !== z.schluessel)
    return rest.length ? rest : [neueZeile()]
  })

  return (
    <FokusFormular formular={formular} titel={`${art.bezeichnung} – ${klasse?.bezeichnung ?? 'alle Instrumentenklassen (allgemein)'}`}
                   onSpeichern={speichern} sendet={sendet} fehler={fehler}
                   zusatz={klasse && (
                     <button type="button" className="btn btn--sekundaer"
                             onClick={() => { formular.markiereGeaendert(); setZeilen((alle) => [...alle, neueZeile()]) }}>
                       Ausführung hinzufügen
                     </button>
                   )}>
      <table className="preisliste__zeilen">
        <thead>
          <tr>
            {klasse && <th>Ausführung</th>}
            <th>Richtpreis in Euro</th>
            <th>Richtzeit in Stunden</th>
            <th>Notiz</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {zeilen.map((z) => {
            const f = zeilenfehler[z.schluessel] ?? {}
            const feld = (fehlerName, eingabe, hinweis) => (
              <td className={f[fehlerName] ? 'feld--fehler' : undefined}>
                {eingabe}
                {f[fehlerName] ? <small className="feld__fehler">{f[fehlerName]}</small> : hinweis && <small>{hinweis}</small>}
              </td>
            )
            return (
              <Fragment key={z.schluessel}>
                <tr>
                  {klasse && feld('ausfuehrung',
                    <input aria-label="Ausführung" value={z.ausfuehrung} maxLength={100} autoComplete="off"
                           placeholder="Standard" onChange={(e) => aendern(z.schluessel, 'ausfuehrung', e.target.value)} />)}
                  {feld('vorgabe_kosten',
                    <input aria-label="Richtpreis in Euro" type="number" min="0" step="0.01" value={z.preis}
                           onChange={(e) => aendern(z.schluessel, 'preis', e.target.value)}
                           onBlur={() => zeitVorschlagen(z.schluessel)} />)}
                  {feld('vorgabe_stunden',
                    <input aria-label="Richtzeit in Stunden" type="number" min="0" step="0.25" value={z.zeit}
                           onChange={(e) => aendern(z.schluessel, 'zeit', e.target.value)} />,
                    z.vorschlag && `Vorschlag: Preis ÷ Stundensatz (${euro(stundensatz)})`)}
                  {feld('notiz',
                    <input aria-label="Notiz" value={z.notiz} autoComplete="off"
                           onChange={(e) => aendern(z.schluessel, 'notiz', e.target.value)} />)}
                  <td className="zeilenaktionen">
                    {z.id
                      ? <button type="button" className="btn btn--klein btn--gefahr" onClick={() => archivieren(z)}>Archivieren</button>
                      : zeilen.length > 1 && <button type="button" className="btn btn--klein btn--sekundaer" onClick={() => entfernen(z)}>Entfernen</button>}
                  </td>
                </tr>
                {f.allgemein && <tr><td colSpan={5} className="meldung--fehler">{f.allgemein}</td></tr>}
                {archivFrage === z.schluessel && (
                  <tr>
                    <td colSpan={5}>
                      <div className="rueckfrage" role="alert">
                        <p>{instrumenteHinweis(z.instrumente)}</p>
                        <button type="button" className="btn btn--gefahr btn--klein" onClick={() => archivieren(z, true)}>Trotzdem archivieren</button>
                        <button type="button" className="btn btn--sekundaer btn--klein" onClick={() => setArchivFrage(null)}>Abbrechen</button>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
      {ohneStandard && (
        <p className="meldung preisliste__ohne-standard">
          Kein Standardwert hinterlegt: Für Instrumente ohne Ausführung {allgemein
            ? `gilt der allgemeine Wert (${euro(allgemein.vorgabe_kosten)}, ${stunden(allgemein.vorgabe_stunden)}).`
            : 'gibt es keinen Richtpreis, auch keinen allgemeinen.'}
        </p>
      )}
      <p className="leise klein">
        {klasse
          ? 'Ausführung leer = Standardausführung. Weitere Zeilen nur für Varianten desselben Instruments (Oberfläche, Ventilmechanik).'
          : 'Der allgemeine Wert gilt für alle Instrumentenklassen ohne eigenen Wert.'}
        {' '}Lässt du die Richtzeit leer, wird sie aus Preis ÷ Stundensatz vorgeschlagen.
      </p>
    </FokusFormular>
  )
}

// Der Standard einer Zelle: bei mehreren Ausführungen die gekennzeichnete, sonst der einzige Wert (2.6a)
const standardVon = (werte) => werte.find((w) => w.ist_standard) ?? werte.find((w) => w.ausfuehrung === null)

// Inhalt einer Zelle: Richtpreis, darunter klein die Richtzeit; bei mehreren Ausführungen ein Zusatz
function Zellinhalt({ werte, allgemein }) {
  const standard = standardVon(werte)
  const ausfuehrungen = werte.length - (standard ? 1 : 0)
  if (standard) {
    return (
      <>
        <span className="preisliste__preis">{euro(standard.vorgabe_kosten)}</span>
        <span className="preisliste__zeit">{stunden(standard.vorgabe_stunden)}</span>
        {ausfuehrungen > 0 && <span className="preisliste__zusatz">+ {ausfuehrungen} {ausfuehrungen === 1 ? 'Ausführung' : 'Ausführungen'}</span>}
      </>
    )
  }
  if (ausfuehrungen > 0) {
    const guenstigste = werte.reduce((a, b) => (b.vorgabe_kosten < a.vorgabe_kosten ? b : a))
    return (
      <>
        <span className="preisliste__preis">ab {euro(guenstigste.vorgabe_kosten)}</span>
        <span className="preisliste__zeit">{stunden(guenstigste.vorgabe_stunden)}</span>
        <span className="preisliste__zusatz">{ausfuehrungen} {ausfuehrungen === 1 ? 'Ausführung' : 'Ausführungen'}</span>
      </>
    )
  }
  return (
    <>
      <span className="preisliste__leer">–</span>
      {allgemein && <span className="preisliste__zusatz">allgemein {euro(allgemein.vorgabe_kosten)}</span>}
    </>
  )
}

function zellBeschreibung(zeilenName, art, werte, allgemein) {
  const standard = standardVon(werte)
  const inhalt = standard ? `${euro(standard.vorgabe_kosten)}, ${stunden(standard.vorgabe_stunden)}`
    : werte.length ? `${werte.length} Ausführungen`
    : allgemein ? `kein eigener Wert, es gilt der allgemeine Wert ${euro(allgemein.vorgabe_kosten)}` : 'kein Wert'
  return `${zeilenName}, ${art.bezeichnung}: ${inhalt}`
}

export default function Preisliste() {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [daten, setDaten] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [sucheKlasse, setSucheKlasse] = useState('')
  const [sucheArt, setSucheArt] = useState('')
  const [eingeklappt, setEingeklappt] = useState(() => new Set())

  const laden = useCallback(() => Promise.all([
    alleEintraege(api.admin.klassen),
    alleEintraege(api.admin.arten),
    alleEintraege(api.admin.vorgabewerte),
    api.admin.einstellungen(),
  ])
    .then(([klassen, arten, werte, einstellungen]) => {
      const satz = Number(einstellungen.find((e) => e.schluessel === 'stundensatz')?.wert)
      setDaten({ klassen, arten, werte, stundensatz: satz > 0 ? satz : null })
    })
    .catch((e) => setFehler(e.message)), [])
  useEffect(() => { laden() }, [laden])

  // Werte je Zelle: "klasseId|artId" → aktive Richtpreise (Standard und Ausführungen)
  const jeZelle = useMemo(() => {
    const karte = new Map()
    for (const w of daten?.werte ?? []) {
      const schluessel = zellSchluessel(w.instrumentenklasse_id ?? ALLGEMEIN, w.reparaturart_id)
      karte.set(schluessel, [...(karte.get(schluessel) ?? []), w])
    }
    return karte
  }, [daten])

  if (fehler) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!daten) return <p className="leise">Lädt …</p>

  const arten = daten.arten.filter((a) => enthaelt(a.bezeichnung, sucheArt))
  const klassen = daten.klassen.filter((k) => enthaelt(`${k.bezeichnung} ${k.oberkategorie}`, sucheKlasse))
  const gruppen = []
  for (const k of klassen) {
    const letzte = gruppen[gruppen.length - 1]
    if (letzte?.name === k.oberkategorie) letzte.klassen.push(k)
    else gruppen.push({ name: k.oberkategorie, klassen: [k] })
  }
  const spalten = arten.length + 1

  function umklappen(name) {
    setEingeklappt((alt) => {
      const neu = new Set(alt)
      if (neu.has(name)) neu.delete(name); else neu.add(name)
      return neu
    })
  }

  function angelegt(eintrag, text) {
    formular.gespeichert()
    rueckmeldung(`${text} „${eintrag.bezeichnung}“ angelegt`)
    if (eintrag.oberkategorie) setEingeklappt((alt) => new Set([...alt].filter((n) => n !== eintrag.oberkategorie)))
    setSucheKlasse(''); setSucheArt('')
    laden()
    hervorheben(eintrag.id)
  }

  function Zeile({ id, name, klasse }) {
    const offeneArt = arten.find((a) => formular.offen === zellSchluessel(id, a.id))
    return (
      <>
        <tr className={id === hervorgehoben ? 'zeile--hervorgehoben' : undefined}>
          <th scope="row">{name}</th>
          {arten.map((a) => {
            const schluessel = zellSchluessel(id, a.id)
            const werte = jeZelle.get(schluessel) ?? []
            const allgemein = klasse ? jeZelle.get(zellSchluessel(ALLGEMEIN, a.id))?.[0] : null
            const klassen_ = ['preisliste__zelle', formular.offen === schluessel && 'preisliste__zelle--offen',
              (hervorgehoben === schluessel || hervorgehoben === a.id) && 'hervorgehoben'].filter(Boolean).join(' ')
            return (
              <td key={a.id} className={klassen_}>
                <button type="button" aria-expanded={formular.offen === schluessel}
                        aria-label={zellBeschreibung(name, a, werte, allgemein)}
                        title={!werte.length ? (allgemein ? 'Kein eigener Wert – es gilt der allgemeine Wert' : 'Kein Wert hinterlegt') : undefined}
                        onClick={() => formular.oeffnen(schluessel)}>
                  <Zellinhalt werte={werte} allgemein={allgemein} />
                </button>
              </td>
            )
          })}
        </tr>
        {offeneArt && (
          <tr className="preisliste__editor">
            <td colSpan={spalten}>
              <div className="preisliste__editor-inhalt">
                {formular.rueckfrageOffen && <Rueckfrage formular={formular} />}
                <ZellenEditor key={formular.offen} formular={formular} klasse={klasse} art={offeneArt}
                              werte={jeZelle.get(formular.offen) ?? []}
                              allgemein={klasse ? jeZelle.get(zellSchluessel(ALLGEMEIN, offeneArt.id))?.[0] : null} stundensatz={daten.stundensatz}
                              onGeaendert={laden}
                              onFertig={() => { const s = formular.offen; formular.gespeichert(); hervorheben(s) }} />
              </div>
            </td>
          </tr>
        )}
      </>
    )
  }

  return (
    <>
      <div className="kopf"><h1>Preisliste</h1></div>
      <p className="leise seitenbeschreibung">
        Richtpreis und Richtzeit je Instrumentenklasse und Reparaturart. Ein Klick auf eine Zelle öffnet sie zum
        Bearbeiten. <Link to="/verwaltung/vorgabewerte">Als Liste anzeigen</Link> (auch archivierte Werte). Umbenennen
        und Archivieren: <Link to="/verwaltung/instrumentenklassen">Instrumentenklassen</Link>,{' '}
        <Link to="/verwaltung/reparaturarten">Reparaturarten</Link>.
      </p>

      <div className="aktionsleiste">
        <AktionsButton formular={formular} schluessel={KLASSE_NEU}>Instrumentenklasse hinzufügen</AktionsButton>
        <AktionsButton formular={formular} schluessel={ART_NEU}>Reparaturart hinzufügen</AktionsButton>
      </div>
      {!istZelle(formular.offen) && (
        <FormularBereich formular={formular}>
          {formular.offen === KLASSE_NEU && (
            <NeuFormular key={KLASSE_NEU} formular={formular} titel="Neue Instrumentenklasse" speichernText="Instrumentenklasse anlegen"
                         Felder={KlasseFelder} startwerte={{ bezeichnung: '', oberkategorie: '' }}
                         zuDaten={(w) => ({ bezeichnung: w.bezeichnung, oberkategorie: w.oberkategorie })}
                         anlegen={api.admin.klasseAnlegen} onGespeichert={(e) => angelegt(e, 'Instrumentenklasse')} />
          )}
          {formular.offen === ART_NEU && (
            <NeuFormular key={ART_NEU} formular={formular} titel="Neue Reparaturart" speichernText="Reparaturart anlegen"
                         Felder={ArtFelder} startwerte={{ bezeichnung: '', standard_komplexitaet: '2' }}
                         zuDaten={(w) => ({ bezeichnung: w.bezeichnung, standard_komplexitaet: Number(w.standard_komplexitaet) })}
                         anlegen={api.admin.artAnlegen} onGespeichert={(e) => angelegt(e, 'Reparaturart')} />
          )}
        </FormularBereich>
      )}

      <div className="filterleiste">
        <input type="search" value={sucheKlasse} onChange={(e) => setSucheKlasse(e.target.value)}
               placeholder="Instrumentenklasse oder Oberkategorie suchen" aria-label="Instrumentenklasse suchen" />
        <input type="search" value={sucheArt} onChange={(e) => setSucheArt(e.target.value)}
               placeholder="Reparaturart suchen" aria-label="Reparaturart suchen" />
      </div>

      {daten.arten.length === 0 && <p className="leise">Noch keine Reparaturarten – über „Reparaturart hinzufügen“ anlegen.</p>}
      {daten.arten.length > 0 && arten.length === 0 && <p className="leise">Keine Reparaturart passt zur Suche.</p>}
      {arten.length > 0 && (
        <div className="preisliste">
          <table className="preisliste__tabelle">
            <thead>
              <tr>
                <th scope="col">Instrumentenklasse</th>
                {arten.map((a) => <th key={a.id} scope="col" className={hervorgehoben === a.id ? 'hervorgehoben' : undefined}>{a.bezeichnung}</th>)}
              </tr>
            </thead>
            <tbody>
              {!sucheKlasse.trim() && Zeile({ id: ALLGEMEIN, name: 'Allgemein (alle Instrumentenklassen)', klasse: null })}
            </tbody>
            {gruppen.map((g) => {
              const zu = eingeklappt.has(g.name) && !sucheKlasse.trim()
              return (
                <tbody key={g.name}>
                  <tr className="preisliste__gruppe">
                    <th scope="rowgroup">
                      <button type="button" aria-expanded={!zu} onClick={() => umklappen(g.name)}>
                        <span aria-hidden="true">{zu ? '▸' : '▾'}</span> {g.name} <span className="leise">({g.klassen.length})</span>
                      </button>
                    </th>
                    <td colSpan={arten.length}></td>
                  </tr>
                  {!zu && g.klassen.map((k) => <Fragment key={k.id}>{Zeile({ id: k.id, name: k.bezeichnung, klasse: k })}</Fragment>)}
                </tbody>
              )
            })}
          </table>
          {klassen.length === 0 && <p className="leise preisliste__hinweis">
            {daten.klassen.length ? 'Keine Instrumentenklasse passt zur Suche.' : 'Noch keine Instrumentenklassen – über „Instrumentenklasse hinzufügen“ anlegen.'}
          </p>}
        </div>
      )}
    </>
  )
}
