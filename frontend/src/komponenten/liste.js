// Zustand einer Liste nach Datenmodell 9.11: Suche, Filter, Sortierung und Seite stehen in der
// Adresse (bleiben beim Zurückgehen erhalten); Suche/Filter/Sortierung/Blättern macht das Backend.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

export const SUCH_PAUSE_MS = 300

// filter: [{ name, label, standard, optionen: [{ wert, text }] }]
export function useListe({ laden, filter = [], sortierung, richtung = 'auf' }) {
  const [adresse, setAdresse] = useSearchParams()
  const [daten, setDaten] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [neuLadenZaehler, setNeuLadenZaehler] = useState(0)

  const standard = useMemo(() => ({
    suche: '', sortierung, richtung, seite: '1',
    ...Object.fromEntries(filter.map((f) => [f.name, f.standard ?? ''])),
  }), [filter, sortierung, richtung])

  const wert = useCallback((name) => adresse.get(name) ?? standard[name], [adresse, standard])
  const zustand = useMemo(
    () => Object.fromEntries(Object.keys(standard).map((name) => [name, wert(name)])),
    [standard, wert],
  )

  // Nur Abweichungen vom Standard in die Adresse schreiben (kurze, teilbare Adressen)
  const setzen = useCallback((aenderungen, { seiteZuruecksetzen = true } = {}) => {
    setAdresse((alt) => {
      const neu = new URLSearchParams(alt)
      const alles = seiteZuruecksetzen ? { ...aenderungen, seite: '1' } : aenderungen
      for (const [name, w] of Object.entries(alles)) {
        if (w === undefined || String(w) === String(standard[name])) neu.delete(name)
        else neu.set(name, w)
      }
      return neu
    }, { replace: true })
  }, [setAdresse, standard])

  // Suchfeld: eigene Eingabe, erst nach kurzer Pause in die Adresse (9.11, Punkt 1)
  const [sucheEingabe, setSucheEingabe] = useState(zustand.suche)
  const letzteSuche = useRef(zustand.suche)
  useEffect(() => {
    if (sucheEingabe === letzteSuche.current) return undefined
    const timer = setTimeout(() => { letzteSuche.current = sucheEingabe; setzen({ suche: sucheEingabe.trim() }) }, SUCH_PAUSE_MS)
    return () => clearTimeout(timer)
  }, [sucheEingabe, setzen])

  // Laden bei jeder Änderung des Zustands
  const schluessel = JSON.stringify(zustand)
  useEffect(() => {
    let abgebrochen = false
    const parameter = Object.fromEntries(Object.entries(zustand).filter(([, w]) => w !== ''))
    laden(parameter)
      .then((d) => { if (!abgebrochen) { setDaten(d); setFehler(null) } })
      .catch((e) => { if (!abgebrochen) setFehler(e.message) })
    return () => { abgebrochen = true }
  }, [schluessel, neuLadenZaehler]) // eslint-disable-line react-hooks/exhaustive-deps

  const aktiveFilter = filter
    .filter((f) => String(zustand[f.name]) !== String(f.standard ?? ''))
    .map((f) => ({ ...f, text: f.optionen.find((o) => String(o.wert) === String(zustand[f.name]))?.text ?? zustand[f.name] }))

  return {
    daten, fehler, zustand, filter, aktiveFilter,
    sucheEingabe, setSucheEingabe,
    setzeFilter: (name, w) => setzen({ [name]: w }),
    entferneSuche: () => { letzteSuche.current = ''; setSucheEingabe(''); setzen({ suche: '' }) },
    zuruecksetzen: () => {
      letzteSuche.current = ''
      setSucheEingabe('')
      setzen(Object.fromEntries(Object.keys(standard).filter((n) => n !== 'sortierung' && n !== 'richtung').map((n) => [n, standard[n]])))
    },
    sortiere: (spalte) => setzen({
      sortierung: spalte,
      richtung: zustand.sortierung === spalte && zustand.richtung === 'auf' ? 'ab' : 'auf',
    }),
    zurSeite: (seite) => setzen({ seite: String(seite) }, { seiteZuruecksetzen: false }),
    neuLaden: () => setNeuLadenZaehler((n) => n + 1),
    gefiltert: Boolean(zustand.suche) || aktiveFilter.length > 0,
  }
}
