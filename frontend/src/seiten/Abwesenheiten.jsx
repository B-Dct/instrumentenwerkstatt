// Abwesenheits-Raster (9.13) – nur Werkstattleitung und Admin (7.2).
// Zeilen: "Ganze Werkstatt" + aktive Mitarbeiter; Spalten: die Tage einer Woche.
// Jede Zelle zeigt die verfügbaren Tagesstunden (Normalfall: Wochenstunden / 5). Klick auf eine
// Zelle – oder Ziehen über mehrere Tage – öffnet direkt darunter das Eingabefeld.
// Gespeichert werden Wochenstunden (2.3): Tagesstunden × 5; 0 = ganztägig abwesend.
import { Fragment, useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { api, datum, zahl } from '../api.js'
import { Feld, FokusFormular, Rueckfrage } from '../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../komponenten/fokusFormular.js'
import { useHervorhebung } from '../komponenten/hervorhebung.js'
import { useRueckmeldung } from '../komponenten/rueckmeldung.js'
import { leerZuNull, useSpeichern, vorabPruefen } from '../komponenten/speichern.js'

const WERKSTATT = 'werkstatt'
const WERKSTATT_NAME = 'Ganze Werkstatt'
const ARBEITSTAGE = 5
const TYPEN_PERSON = { urlaub: 'Urlaub', krankheit: 'Krankheit', schulung: 'Schulung', reduzierte_stunden: 'Reduzierte Stunden' }
const TYPEN_WERKSTATT = { feiertag: 'Feiertag', betriebsschliessung: 'Betriebsschließung' }
const TYPEN = { ...TYPEN_PERSON, ...TYPEN_WERKSTATT }

// --- Datumshelfer (immer JJJJ-MM-TT in lokaler Zeit) ---------------------------------
const iso = (d) => d.toLocaleDateString('sv-SE')
const alsDatum = (text) => new Date(`${text}T12:00:00`)
const plusTage = (text, n) => { const d = alsDatum(text); d.setDate(d.getDate() + n); return iso(d) }
const montagVon = (text) => plusTage(text, -((alsDatum(text).getDay() + 6) % 7))
const istWochenende = (text) => [0, 6].includes(alsDatum(text).getDay())
const tagKurz = (text) => alsDatum(text).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
const wochentag = (text) => alsDatum(text).toLocaleDateString('de-DE', { weekday: 'short' }).replace('.', '')
const tagMonat = (text) => alsDatum(text).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
function kalenderwoche(text) {
  // ISO 8601: Die Woche gehört zu dem Jahr, in dem ihr Donnerstag liegt
  const donnerstag = alsDatum(text)
  donnerstag.setDate(donnerstag.getDate() + 3 - ((donnerstag.getDay() + 6) % 7))
  const ersterJanuar = new Date(donnerstag.getFullYear(), 0, 1, 12)
  return Math.floor(Math.round((donnerstag - ersterJanuar) / 86400000) / 7) + 1
}
const zeitraum = (von, bis) => (von === bis ? tagKurz(von) : `${tagKurz(von)} – ${tagKurz(bis)}`)

// Verfügbare Tagesstunden einer Abwesenheit (gespeichert sind Wochenstunden)
const tagesstunden = (a) => (a.reduzierte_stunden === null ? 0 : a.reduzierte_stunden / ARBEITSTAGE)
const deckt = (a, tag) => a.von_datum <= tag && tag <= a.bis_datum
const beschreibung = (a) => `${TYPEN[a.typ] ?? a.typ} (${a.mitarbeiter_name ?? WERKSTATT_NAME}, ${zeitraum(a.von_datum, a.bis_datum)})`

// Schlüssel des offenen Eingabefelds: Zeile, Zeitraum und ggf. der bearbeitete Eintrag
const schluesselAus = (zeile, von, bis, eintragId = '') => [zeile, von, bis, eintragId].join('|')
function auswahlAus(schluessel) {
  if (!schluessel) return null
  const [zeile, von, bis, eintragId] = schluessel.split('|')
  return { zeile, von, bis, eintragId: eintragId || null }
}

// --- Eingabefeld unter der Zeile -----------------------------------------------------

function Eingabe({ formular, zeile, name, auswahl, eintrag, normal, storniertAmTag, onGespeichert, onStorno }) {
  const werkstatt = zeile === WERKSTATT
  const typen = werkstatt ? TYPEN_WERKSTATT : TYPEN_PERSON
  const [werte, setWerte] = useState({
    stunden: eintrag ? String(tagesstunden(eintrag)) : '0',
    typ: eintrag?.typ ?? (werkstatt ? 'betriebsschliessung' : 'urlaub'),
    von_datum: eintrag?.von_datum ?? auswahl.von,
    bis_datum: eintrag?.bis_datum ?? auswahl.bis,
    notiz: eintrag?.notiz ?? '',
  })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const stunden = werkstatt ? 0 : Number(werte.stunden)
    vorabPruefen({
      stunden: !werkstatt && (
        (werte.stunden === '' && 'Pflichtfeld (0 = ganztägig abwesend)')
        || (stunden < 0 && 'Mindestens 0')
        || (stunden > 0 && stunden >= normal && `${zahl(normal)} Std. ist der Normalwert – dafür ist kein Eintrag nötig`)),
      typ: werte.typ === 'reduzierte_stunden' && stunden === 0 && 'Bei 0 Stunden bitte Urlaub, Krankheit oder Schulung wählen',
      von_datum: !werte.von_datum && 'Pflichtfeld',
      bis_datum: (!werte.bis_datum && 'Pflichtfeld') || (werte.bis_datum < werte.von_datum && 'Das Ende liegt vor dem Beginn'),
    })
    const daten = {
      mitarbeiter_id: werkstatt ? null : zeile,
      typ: werte.typ,
      von_datum: werte.von_datum,
      bis_datum: werte.bis_datum,
      reduzierte_stunden: stunden > 0 ? Math.round(stunden * ARBEITSTAGE * 100) / 100 : null,
      notiz: leerZuNull(werte.notiz),
    }
    return eintrag ? api.abwesenheitAendern(eintrag.id, daten) : api.abwesenheitAnlegen(daten)
  }, onGespeichert, { konfliktFeld: 'typ' })
  // Die Überschneidungs-Meldung steht am Typ, hängt aber auch am Zeitraum
  const setze = (feld) => (e) => {
    feldGeaendert(feld); feldGeaendert('typ'); feldGeaendert('reduzierte_stunden')
    setWerte((w) => ({ ...w, [feld]: e.target.value }))
  }

  return (
    <FokusFormular formular={formular} sendet={sendet} fehler={fehler} onSpeichern={ausfuehren}
                   titel={`${name}: ${eintrag ? 'Abwesenheit bearbeiten' : 'Abwesenheit eintragen'}`}
                   speichernText={eintrag ? 'Speichern' : 'Eintragen'}
                   zusatz={eintrag && (
                     <button type="button" className="btn btn--gefahr aktionsleiste__rechts" onClick={() => onStorno(eintrag, true)}>
                       Stornieren
                     </button>
                   )}>
      <div className="spalten spalten--eng">
        {!werkstatt && (
          <Feld label="Verfügbare Stunden pro Tag" fehler={felder.stunden ?? felder.reduzierte_stunden}
                hinweis={`0 = ganztägig abwesend. Normal: ${zahl(normal)} Std.`}>
            <input type="number" min="0" max="16" step="0.25" value={werte.stunden} onChange={setze('stunden')} required />
          </Feld>
        )}
        <Feld label="Typ" fehler={felder.typ ?? felder.mitarbeiter_id}
              hinweis={werkstatt ? 'Gilt ganztägig für alle Mitarbeiter' : undefined}>
          <select value={werte.typ} onChange={setze('typ')} required>
            {Object.entries(typen).map(([wert, text]) => <option key={wert} value={wert}>{text}</option>)}
          </select>
        </Feld>
        <Feld label="Von" fehler={felder.von_datum}>
          <input type="date" value={werte.von_datum} onChange={setze('von_datum')} required />
        </Feld>
        <Feld label="Bis (einschließlich)" fehler={felder.bis_datum}>
          <input type="date" value={werte.bis_datum} min={werte.von_datum || undefined} onChange={setze('bis_datum')} required />
        </Feld>
      </div>
      <Feld label="Notiz" fehler={felder.notiz} hinweis="Optional, z. B. „Betriebsurlaub Weihnachten“">
        <input value={werte.notiz} onChange={setze('notiz')} maxLength={500} autoComplete="off" />
      </Feld>
      {storniertAmTag.length > 0 && (
        <ul className="raster__storniert">
          {storniertAmTag.map((a) => (
            <li key={a.id}>
              Storniert: {TYPEN[a.typ] ?? a.typ}, {zeitraum(a.von_datum, a.bis_datum)}{a.notiz ? ` – ${a.notiz}` : ''}{' '}
              <button type="button" className="link-button" onClick={() => onStorno(a, false)}>Wiederherstellen</button>
            </li>
          ))}
        </ul>
      )}
      <p className="leise">
        Neue Terminschätzungen berücksichtigen den Eintrag sofort. Bereits berechnete Termine offener Aufträge werden
        nicht automatisch angepasst (Abschnitt 4.0a).
      </p>
    </FokusFormular>
  )
}

// --- Seite ---------------------------------------------------------------------------

export default function Abwesenheiten() {
  const [adresse, setAdresse] = useSearchParams()
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [raster, setRaster] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [aktionsfehler, setAktionsfehler] = useState(null)
  const [ziehen, setZiehen] = useState(null) // { zeile, start, ende } (Spaltenindex), solange die Maus gedrückt ist

  const heute = iso(new Date())
  const montag = montagVon(adresse.get('woche') ?? heute)
  const stornierte = adresse.get('stornierte') === '1'

  const laden = useCallback(
    () => api.abwesenheitenRaster({ von: montag, tage: 7, stornierte })
      .then((r) => { setRaster(r); setFehler(null) })
      .catch((e) => setFehler(e.message)),
    [montag, stornierte],
  )
  useEffect(() => { laden() }, [laden])

  // Ziehen über mehrere Tage: Loslassen irgendwo beendet die Markierung und öffnet das Eingabefeld
  useEffect(() => {
    if (!ziehen) return undefined
    const loslassen = () => {
      const [a, b] = [Math.min(ziehen.start, ziehen.ende), Math.max(ziehen.start, ziehen.ende)]
      if (a !== b && raster) formular.oeffnen(schluesselAus(ziehen.zeile, raster.tage[a], raster.tage[b]))
      setZiehen(null)
    }
    window.addEventListener('mouseup', loslassen)
    return () => window.removeEventListener('mouseup', loslassen)
  }, [ziehen, raster, formular])

  // Andere Woche / Umschalter: bei ungespeicherten Änderungen erst die Rückfrage
  function adresseAendern(aenderung) {
    if (formular.geaendert) { formular.schliessen(); return }
    formular.gespeichert()
    setAktionsfehler(null)
    setAdresse((alt) => {
      const neu = new URLSearchParams(alt)
      for (const [name, wert] of Object.entries(aenderung)) {
        if (wert === null) neu.delete(name); else neu.set(name, wert)
      }
      return neu
    }, { replace: true })
  }
  const zurWoche = (tag) => adresseAendern({ woche: montagVon(tag) === montagVon(heute) ? null : montagVon(tag) })

  if (fehler && !raster) return <p className="meldung meldung--fehler">{fehler}</p>
  if (!raster) return <p className="leise">Lädt …</p>

  const aktive = raster.abwesenheiten.filter((a) => a.storniert_am === null)
  const storniert = raster.abwesenheiten.filter((a) => a.storniert_am !== null)
  const zeilenId = (a) => a.mitarbeiter_id ?? WERKSTATT
  const zeilen = [{ id: WERKSTATT, name: WERKSTATT_NAME, normalstunden: null }, ...raster.zeilen.map((z) => ({ ...z, id: z.mitarbeiter_id }))]
  const auswahl = auswahlAus(formular.offen)

  // Was eine Zelle zeigt: geschlossen (werkstattweit), Abwesenheit(en) oder der Normalwert
  function zelle(zeile, i) {
    const tag = raster.tage[i]
    const eigene = aktive.filter((a) => zeilenId(a) === zeile.id && deckt(a, tag))
    const stornierteHier = storniert.filter((a) => zeilenId(a) === zeile.id && deckt(a, tag))
    if (istWochenende(tag)) return { art: 'wochenende', eigene: [], stornierteHier }
    if (zeile.id === WERKSTATT) return { art: eigene.length ? 'werkstatt' : 'frei', eigene, stornierteHier }
    const schliessung = aktive.find((a) => a.mitarbeiter_id === null && deckt(a, tag))
    if (schliessung) return { art: 'geschlossen', schliessung, eigene: [], stornierteHier }
    const normal = zeile.normalstunden[i]
    if (!eigene.length) return { art: 'normal', normal, eigene, stornierteHier }
    // Mehrere Einträge am selben Tag (z. B. krank im Urlaub): der mit den wenigsten Stunden zählt
    const massgeblich = [...eigene].sort((a, b) => tagesstunden(a) - tagesstunden(b))[0]
    return { art: 'abwesend', normal, eigene, massgeblich, stunden: Math.min(tagesstunden(massgeblich), normal), stornierteHier }
  }

  function zelleOeffnen(zeile, i) {
    const tag = raster.tage[i]
    const z = zelle(zeile, i)
    const eintrag = z.massgeblich ?? z.eigene[0]
    setAktionsfehler(null)
    formular.oeffnen(schluesselAus(zeile.id, eintrag?.von_datum ?? tag, eintrag?.bis_datum ?? tag, eintrag?.id))
  }

  function gespeichert(eintrag, neu) {
    formular.gespeichert()
    rueckmeldung(`${beschreibung(eintrag)} ${neu ? 'eingetragen' : 'gespeichert'}`)
    hervorheben(eintrag.id)
    laden()
  }

  async function stornoSetzen(eintrag, stornieren) {
    setAktionsfehler(null)
    if (formular.geaendert) {
      setAktionsfehler('Bitte die Eingabe zuerst speichern oder abbrechen.')
      return
    }
    try {
      const neu = await (stornieren ? api.abwesenheitStornieren(eintrag.id) : api.abwesenheitWiederherstellen(eintrag.id))
      formular.gespeichert()
      rueckmeldung(stornieren
        ? `${beschreibung(eintrag)} storniert – die Tage stehen wieder auf dem Normalwert`
        : `${beschreibung(eintrag)} wiederhergestellt`)
      hervorheben(neu.id)
      laden()
    } catch (err) {
      setAktionsfehler(err.message)
    }
  }

  const markiert = (zeile, i) => {
    if (ziehen) return ziehen.zeile === zeile.id && i >= Math.min(ziehen.start, ziehen.ende) && i <= Math.max(ziehen.start, ziehen.ende)
    return auswahl?.zeile === zeile.id && auswahl.von <= raster.tage[i] && raster.tage[i] <= auswahl.bis
  }

  return (
    <>
      <div className="kopf"><h1>Abwesenheiten</h1></div>
      <p className="leise seitenbeschreibung">
        Jede Zelle zeigt die verfügbaren Stunden an diesem Tag. Zum Eintragen auf eine Zelle klicken oder mit gedrückter
        Maustaste über mehrere Tage ziehen. 0 bedeutet ganztägig abwesend.
      </p>

      <div className="aktionsleiste raster__leiste">
        <button type="button" className="btn btn--sekundaer" onClick={() => zurWoche(plusTage(montag, -7))}>‹ Vorwoche</button>
        <button type="button" className="btn btn--sekundaer" onClick={() => zurWoche(heute)} disabled={montag === montagVon(heute)}>Heute</button>
        <button type="button" className="btn btn--sekundaer" onClick={() => zurWoche(plusTage(montag, 7))}>Nächste Woche ›</button>
        <strong aria-live="polite">KW {kalenderwoche(montag)} · {datum(montag)} – {datum(plusTage(montag, 6))}</strong>
        <label className="feld--inline leise aktionsleiste__rechts">
          <input type="checkbox" checked={stornierte} onChange={(e) => adresseAendern({ stornierte: e.target.checked ? '1' : null })} />
          Stornierte anzeigen
        </label>
      </div>
      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {aktionsfehler && <p className="meldung meldung--fehler" role="alert">{aktionsfehler}</p>}

      <div className="tabelle-rahmen">
        <table className="raster">
          <thead>
            <tr>
              <th scope="col">Für</th>
              {raster.tage.map((tag) => (
                <th key={tag} scope="col" className={[istWochenende(tag) && 'raster__wochenende', tag === heute && 'raster__heute'].filter(Boolean).join(' ') || undefined}>
                  <span className="raster__wochentag">{wochentag(tag)}</span> {tagMonat(tag)}{tag === heute && <span className="unsichtbar"> (heute)</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {zeilen.map((zeile) => {
              const offen = auswahl?.zeile === zeile.id
              const eintrag = offen && auswahl.eintragId ? aktive.find((a) => a.id === auswahl.eintragId) : null
              const ersterTag = offen ? Math.max(0, raster.tage.indexOf(auswahl.von)) : 0
              return (
                <Fragment key={zeile.id}>
                  <tr className={zeile.id === WERKSTATT ? 'raster__werkstatt' : undefined}>
                    <th scope="row">{zeile.name}</th>
                    {raster.tage.map((tag, i) => {
                      const z = zelle(zeile, i)
                      const klassen = ['raster__zelle', `raster__zelle--${z.art}`, markiert(zeile, i) && 'raster__zelle--markiert',
                        z.eigene.some((a) => a.id === hervorgehoben) && 'hervorgehoben'].filter(Boolean).join(' ')
                      const stornoMarke = stornierte && z.stornierteHier.length > 0 && <span className="raster__storno">storniert</span>
                      if (z.art === 'wochenende' || z.art === 'geschlossen') {
                        return (
                          <td key={tag} className={klassen}>
                            {z.art === 'geschlossen' && (
                              <span className="raster__typ" title={[TYPEN[z.schliessung.typ], z.schliessung.notiz].filter(Boolean).join(': ')}>geschlossen</span>
                            )}
                          </td>
                        )
                      }
                      const eintragHier = z.massgeblich ?? z.eigene[0]
                      return (
                        <td key={tag} className={klassen}>
                          <button type="button" aria-expanded={offen && markiert(zeile, i)}
                                  title={eintragHier?.notiz ?? undefined}
                                  aria-label={`${zeile.name}, ${tagKurz(tag)}: ${[
                                    z.art === 'normal' && `${zahl(z.normal)} Stunden, kein Eintrag`,
                                    z.art === 'frei' && 'kein Eintrag',
                                    z.art === 'abwesend' && `${zahl(z.stunden)} Stunden, ${TYPEN[eintragHier.typ]}`,
                                    z.art === 'werkstatt' && `geschlossen, ${TYPEN[eintragHier.typ]}`,
                                  ].find(Boolean)}`}
                                  onMouseDown={(e) => { if (e.button === 0) setZiehen({ zeile: zeile.id, start: i, ende: i }) }}
                                  onMouseEnter={() => { if (ziehen?.zeile === zeile.id && !istWochenende(tag)) setZiehen((alt) => alt && { ...alt, ende: i }) }}
                                  onClick={() => zelleOeffnen(zeile, i)}>
                            {z.art === 'normal' && <span className="raster__wert">{zahl(z.normal)}</span>}
                            {z.art === 'frei' && <span className="raster__wert">–</span>}
                            {z.art === 'abwesend' && <span className="raster__wert">{zahl(z.stunden)}</span>}
                            {eintragHier && (
                              <span className="raster__typ">
                                {/* Werkstatt-Zeile: der Name sagt mehr als der Typ (z. B. „Fronleichnam“ statt „Feiertag“) */}
                                {zeile.id === WERKSTATT && eintragHier.notiz
                                  ? eintragHier.notiz
                                  : <>{TYPEN[eintragHier.typ]}{eintragHier.notiz && ' ✎'}</>}
                                {z.eigene.length > 1 && ` +${z.eigene.length - 1}`}
                              </span>
                            )}
                            {stornoMarke}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                  {offen && (
                    <tr className="raster__eingabe">
                      <td colSpan={raster.tage.length + 1}>
                        {formular.rueckfrageOffen && <Rueckfrage formular={formular} />}
                        <Eingabe key={formular.offen} formular={formular} zeile={zeile.id} name={zeile.name} auswahl={auswahl}
                                 eintrag={eintrag} normal={zeile.normalstunden?.[ersterTag] ?? 0}
                                 storniertAmTag={storniert.filter((a) => zeilenId(a) === zeile.id && a.von_datum <= auswahl.bis && a.bis_datum >= auswahl.von)}
                                 onGespeichert={(e) => gespeichert(e, !eintrag)} onStorno={stornoSetzen} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      {formular.rueckfrageOffen && !auswahl && <Rueckfrage formular={formular} />}
      {raster.zeilen.length === 0 && <p className="leise">Es gibt noch keine aktiven Mitarbeiter.</p>}
    </>
  )
}
