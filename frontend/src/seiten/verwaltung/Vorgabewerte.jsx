// Preisliste als Liste: Richtpreise und Richtzeiten (2.6a, 9.17) – nur Admin (7.2), nach 9.10 aufgebaut,
// Liste nach 9.11. Die Matrix-Ansicht derselben Daten ist Preisliste.jsx (9.15).
// Ein Wert gilt allgemein für eine Reparaturart oder speziell für eine Instrumentenklasse.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { alleEintraege, api, datum, euro, zahl } from '../../api.js'
import { AktionsButton, Feld, FokusFormular, FormularBereich } from '../../komponenten/FokusFormular.jsx'
import { useFokusFormular } from '../../komponenten/fokusFormular.js'
import { useHervorhebung } from '../../komponenten/hervorhebung.js'
import { ListeLeer, Listenkopf, Seitenwahl, SortierKopf } from '../../komponenten/Liste.jsx'
import { useListe } from '../../komponenten/liste.js'
import { useRueckmeldung } from '../../komponenten/rueckmeldung.js'
import { leerZuNull, useSpeichern } from '../../komponenten/speichern.js'

const NEU = 'neu'
const ALLGEMEIN = ''

const STATUS_FILTER = { name: 'status', label: 'Status', standard: 'aktiv', optionen: [
  { wert: 'aktiv', text: 'aktiv' }, { wert: 'archiviert', text: 'archiviert' }, { wert: 'alle', text: 'alle' },
] }

// Filter nach Reparaturart und Instrumentenklasse – Optionen kommen aus den Stammdaten (auch archivierte)
function filterAus(arten, klassen) {
  const optionen = (liste) => [
    { wert: '', text: 'alle' },
    ...liste.map((e) => ({ wert: e.id, text: e.archiviert_am ? `${e.bezeichnung} (archiviert)` : e.bezeichnung })),
  ]
  return [
    { name: 'reparaturart_id', label: 'Reparaturart', standard: '', optionen: optionen(arten) },
    { name: 'instrumentenklasse_id', label: 'Instrumentenklasse', standard: '', optionen: optionen(klassen) },
    STATUS_FILTER,
  ]
}

// Aktive Einträge zur Auswahl; ein bereits verknüpfter archivierter Eintrag bleibt sichtbar
function auswahl(liste, aktuelleId) {
  return liste
    .filter((e) => e.archiviert_am === null || e.id === aktuelleId)
    .map((e) => ({ id: e.id, text: e.archiviert_am ? `${e.bezeichnung} (archiviert)` : e.bezeichnung }))
}

// "Trompete, Perinet, versilbert" / "Trompete" / "allgemein"
const geltung = (e) => [e.instrumentenklasse_bezeichnung ?? 'allgemein', e.ausfuehrung].filter(Boolean).join(', ')

// Aufeinanderfolgende Einträge derselben Reparaturart und Instrumentenklasse bilden eine Gruppe:
// mehrere Ausführungen stehen als Unterzeilen unter einer gemeinsamen Überschrift (2.6a, 9.12)
function gruppieren(eintraege) {
  const gruppen = []
  for (const e of eintraege) {
    const letzte = gruppen[gruppen.length - 1]
    if (letzte && e.instrumentenklasse_id && letzte[0].reparaturart_id === e.reparaturart_id
        && letzte[0].instrumentenklasse_id === e.instrumentenklasse_id) letzte.push(e)
    else gruppen.push([e])
  }
  return gruppen
}

function VorgabewertFormular({ formular, eintrag, arten, klassen, onGespeichert }) {
  const [werte, setWerte] = useState({
    reparaturart_id: eintrag?.reparaturart_id ?? '',
    instrumentenklasse_id: eintrag?.instrumentenklasse_id ?? ALLGEMEIN,
    ausfuehrung: eintrag?.ausfuehrung ?? '',
    vorgabe_stunden: eintrag?.vorgabe_stunden ?? '',
    vorgabe_kosten: eintrag?.vorgabe_kosten ?? '',
    notiz: eintrag?.notiz ?? '',
  })
  const { sendet, fehler, felder, ausfuehren, feldGeaendert } = useSpeichern(() => {
    const daten = {
      reparaturart_id: werte.reparaturart_id || null,
      instrumentenklasse_id: werte.instrumentenklasse_id || null,
      ausfuehrung: werte.instrumentenklasse_id ? leerZuNull(werte.ausfuehrung) : null,
      vorgabe_stunden: werte.vorgabe_stunden === '' ? null : Number(werte.vorgabe_stunden),
      vorgabe_kosten: werte.vorgabe_kosten === '' ? null : Number(werte.vorgabe_kosten),
      notiz: leerZuNull(werte.notiz),
    }
    return eintrag ? api.admin.vorgabewertAendern(eintrag.id, daten) : api.admin.vorgabewertAnlegen(daten)
  }, onGespeichert, { konfliktFeld: 'instrumentenklasse_id' })
  const setze = (feld) => (e) => { feldGeaendert(feld); setWerte((w) => ({ ...w, [feld]: e.target.value })) }

  return (
    <FokusFormular formular={formular} titel={eintrag ? 'Richtpreis bearbeiten' : 'Neuer Richtpreis'}
                   onSpeichern={ausfuehren} sendet={sendet} fehler={fehler}
                   speichernText={eintrag ? 'Speichern' : 'Richtpreis anlegen'}>
      <div className="spalten spalten--eng">
        <Feld label="Reparaturart" fehler={felder.reparaturart_id}>
          <select value={werte.reparaturart_id} onChange={setze('reparaturart_id')} required>
            <option value="">Bitte wählen</option>
            {auswahl(arten, eintrag?.reparaturart_id).map((a) => <option key={a.id} value={a.id}>{a.text}</option>)}
          </select>
        </Feld>
        <Feld label="Gilt für" fehler={felder.instrumentenklasse_id}
              hinweis="Ein spezieller Wert hat Vorrang vor dem allgemeinen">
          <select value={werte.instrumentenklasse_id} onChange={setze('instrumentenklasse_id')}>
            <option value={ALLGEMEIN}>Allgemein (alle Instrumentenklassen)</option>
            {auswahl(klassen, eintrag?.instrumentenklasse_id).map((k) => <option key={k.id} value={k.id}>nur {k.text}</option>)}
          </select>
        </Feld>
        {werte.instrumentenklasse_id !== ALLGEMEIN && (
          <Feld label="Ausführung" fehler={felder.ausfuehrung}
                hinweis="Optional, z. B. „Perinet, versilbert“. Leer = Standardausführung. Nur für Varianten desselben Instruments (Oberfläche, Ventilmechanik) – ein anderes Instrument ist eine eigene Instrumentenklasse.">
            <input value={werte.ausfuehrung} onChange={setze('ausfuehrung')} maxLength={100} autoComplete="off" />
          </Feld>
        )}
        <Feld label="Richtzeit in Stunden" fehler={felder.vorgabe_stunden}>
          <input type="number" min="0" step="0.25" value={werte.vorgabe_stunden} onChange={setze('vorgabe_stunden')} required />
        </Feld>
        <Feld label="Richtpreis in Euro" fehler={felder.vorgabe_kosten} hinweis="Preis für den Kunden inkl. üblicher Materialpauschale">
          <input type="number" min="0" step="0.01" value={werte.vorgabe_kosten} onChange={setze('vorgabe_kosten')} required />
        </Feld>
      </div>
      <Feld label="Notiz" fehler={felder.notiz} hinweis="Optional, z. B. „inkl. Standardsaiten“">
        <input value={werte.notiz} onChange={setze('notiz')} autoComplete="off" />
      </Feld>
    </FokusFormular>
  )
}

export default function Vorgabewerte() {
  const formular = useFokusFormular()
  const rueckmeldung = useRueckmeldung()
  const [hervorgehoben, hervorheben] = useHervorhebung()
  const [aktionsfehler, setAktionsfehler] = useState(null)
  const [arten, setArten] = useState([])
  const [klassen, setKlassen] = useState([])
  const [stammdatenFehler, setStammdatenFehler] = useState(null)
  const filter = useMemo(() => filterAus(arten, klassen), [arten, klassen])
  const liste = useListe({ laden: api.admin.vorgabewerte, filter, sortierung: 'reparaturart' })
  const eintraege = liste.daten?.eintraege
  const fehler = liste.fehler ?? stammdatenFehler

  useEffect(() => {
    Promise.all([
      alleEintraege(api.admin.arten, { status: 'alle' }),
      alleEintraege(api.admin.klassen, { status: 'alle' }),
    ])
      .then(([a, k]) => { setArten(a); setKlassen(k) })
      .catch((e) => setStammdatenFehler(e.message))
  }, [])

  const istArchiviert = (stammdaten, id) => stammdaten.find((e) => e.id === id)?.archiviert_am != null

  function gespeichert(eintrag, neu) {
    formular.gespeichert()
    const fuer = geltung(eintrag)
    rueckmeldung(`Richtpreis ${eintrag.reparaturart_bezeichnung} (${fuer}) ${neu ? 'angelegt' : 'gespeichert'}`)
    liste.neuLaden()
    hervorheben(eintrag.id)
  }

  async function archivStatus(eintrag, archiv) {
    setAktionsfehler(null)
    if (formular.geaendert) {
      setAktionsfehler('Bitte das offene Formular zuerst speichern oder abbrechen.')
      return
    }
    formular.gespeichert()
    const name = `${eintrag.reparaturart_bezeichnung} (${geltung(eintrag)})`
    try {
      await (archiv ? api.admin.vorgabewertArchivieren(eintrag.id) : api.admin.vorgabewertReaktivieren(eintrag.id))
      rueckmeldung(archiv
        ? `Richtpreis ${name} archiviert – die Schätzung ignoriert ihn, er kann reaktiviert werden`
        : `Richtpreis ${name} reaktiviert`)
      liste.neuLaden()
      hervorheben(eintrag.id)
    } catch (err) {
      setAktionsfehler(err.message)
    }
  }

  const offenerEintrag = eintraege?.find((e) => e.id === formular.offen && e.archiviert_am === null)

  return (
    <>
      <div className="kopf"><h1>Preisliste als Liste</h1></div>
      <p className="leise seitenbeschreibung">
        Richtpreis und Richtzeit je Reparaturart. Sie gelten, solange es weniger als fünf abgeschlossene
        Vergleichsaufträge gibt; danach rechnet die Schätzung mit dem historischen Durchschnitt. Archivierte Werte
        ignoriert die Schätzung. <Link to="/verwaltung/preisliste">Als Matrix anzeigen</Link>
      </p>

      <div className="aktionsleiste">
        <AktionsButton formular={formular} schluessel={NEU} primaer>Neuer Richtpreis</AktionsButton>
      </div>
      {aktionsfehler && <p className="meldung meldung--fehler" role="alert">{aktionsfehler}</p>}
      <FormularBereich formular={formular}>
        {formular.offen === NEU && (
          <VorgabewertFormular key={NEU} formular={formular} arten={arten} klassen={klassen}
                               onGespeichert={(e) => gespeichert(e, true)} />
        )}
        {offenerEintrag && (
          <VorgabewertFormular key={offenerEintrag.id} formular={formular} eintrag={offenerEintrag}
                               arten={arten} klassen={klassen} onGespeichert={(e) => gespeichert(e, false)} />
        )}
      </FormularBereich>

      <Listenkopf liste={liste} suchhinweis="Suchen: Reparaturart, Instrument, Ausführung, Notiz" />

      {fehler && <p className="meldung meldung--fehler">{fehler}</p>}
      {!liste.daten && !fehler && <p className="leise">Lädt …</p>}
      <ListeLeer liste={liste} leerText="Noch keine Richtpreise angelegt – über „Neuer Richtpreis“ anlegen." />
      {eintraege?.length > 0 && (
        <div className="tabelle-rahmen">
          <table className="tabelle tabelle--klickbar">
            <thead>
              <tr>
                <SortierKopf liste={liste} spalte="reparaturart">Reparaturart</SortierKopf>
                <SortierKopf liste={liste} spalte="gilt_fuer">Gilt für</SortierKopf>
                <SortierKopf liste={liste} spalte="vorgabe_stunden" zahl>Richtzeit (Std.)</SortierKopf>
                <SortierKopf liste={liste} spalte="vorgabe_kosten" zahl>Richtpreis</SortierKopf>
                <th>Notiz</th>
                <SortierKopf liste={liste} spalte="geaendert_am">Geändert</SortierKopf>
                <th></th>
              </tr>
            </thead>
            {gruppieren(eintraege).map((gruppe) => {
              const mehrere = gruppe.length > 1
              const erster = gruppe[0]
              return (
                <tbody key={erster.id} className={mehrere ? 'gruppe' : undefined}>
                  {mehrere && (
                    <tr className="gruppe__kopf zeile--nicht-klickbar">
                      <th scope="rowgroup">
                        {erster.reparaturart_bezeichnung}
                        {istArchiviert(arten, erster.reparaturart_id) && <span className="marke">Reparaturart archiviert</span>}
                      </th>
                      <th scope="rowgroup">
                        {erster.instrumentenklasse_bezeichnung}
                        {istArchiviert(klassen, erster.instrumentenklasse_id) && <span className="marke">Klasse archiviert</span>}
                      </th>
                      <td colSpan={5} className="leise">{gruppe.length} Ausführungen</td>
                    </tr>
                  )}
                  {gruppe.map((e) => {
                    const archiviert = e.archiviert_am !== null
                    // In einer Gruppe heißt die Zeile nach ihrer Ausführung, sonst nach der Reparaturart
                    const name = mehrere ? e.ausfuehrung ?? 'Standard' : e.reparaturart_bezeichnung
                    return (
                      <tr key={e.id} onClick={archiviert ? undefined : () => formular.oeffnen(e.id)}
                          className={[e.id === hervorgehoben && 'zeile--hervorgehoben', formular.offen === e.id && 'zeile--ausgewaehlt',
                            archiviert && 'zeile--archiviert zeile--nicht-klickbar'].filter(Boolean).join(' ') || undefined}>
                        <td colSpan={mehrere ? 2 : 1} className={mehrere ? 'gruppe__unterzeile' : undefined}>
                          {archiviert
                            ? name
                            : <button type="button" className="link-button" aria-expanded={formular.offen === e.id}
                                      onClick={(ev) => { ev.stopPropagation(); formular.oeffnen(e.id) }}>
                                {name}
                              </button>}
                          {!mehrere && istArchiviert(arten, e.reparaturart_id) && <span className="marke">Reparaturart archiviert</span>}
                        </td>
                        {!mehrere && (
                          <td>
                            {e.instrumentenklasse_bezeichnung ? geltung(e) : <span className="leise">allgemein</span>}
                            {istArchiviert(klassen, e.instrumentenklasse_id) && <span className="marke">Klasse archiviert</span>}
                          </td>
                        )}
                        <td className="zahl">{zahl(e.vorgabe_stunden)}</td>
                        <td className="zahl">{euro(e.vorgabe_kosten)}</td>
                        <td>{e.notiz ?? ''}</td>
                        <td>{datum(e.geaendert_am)}</td>
                        <td className="zeilenaktionen">
                          {archiviert && <span className="marke">archiviert</span>}
                          <button type="button" className={`btn btn--klein ${archiviert ? 'btn--sekundaer' : 'btn--gefahr'}`}
                                  onClick={(ev) => { ev.stopPropagation(); archivStatus(e, !archiviert) }}>
                            {archiviert ? 'Reaktivieren' : 'Archivieren'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              )
            })}
          </table>
        </div>
      )}
      <Seitenwahl liste={liste} />
    </>
  )
}
