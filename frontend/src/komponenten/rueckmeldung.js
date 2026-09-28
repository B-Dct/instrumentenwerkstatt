// Kontext und Hook für die Erfolgsbestätigung (Komponente: Rueckmeldung.jsx)
import { createContext, useContext } from 'react'

export const RueckmeldungKontext = createContext(() => {})
export const useRueckmeldung = () => useContext(RueckmeldungKontext)
