// Geänderten Eintrag kurz hervorheben (Datenmodell 9.10, Regel 5)
import { useCallback, useEffect, useRef, useState } from 'react'

const DAUER_MS = 2500

export function useHervorhebung() {
  const [id, setId] = useState(null)
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  const hervorheben = useCallback((neueId) => {
    clearTimeout(timer.current)
    setId(neueId)
    timer.current = setTimeout(() => setId(null), DAUER_MS)
  }, [])
  return [id, hervorheben]
}
