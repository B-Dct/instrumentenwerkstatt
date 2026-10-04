import { useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { abmelden, angemeldeterNutzer, hatRolle, nutzerAktualisieren } from './api.js'
import { RueckmeldungBereich } from './komponenten/Rueckmeldung.jsx'

const ROLLEN = { mitarbeiter: 'Mitarbeiter', werkstattleiter: 'Werkstattleitung', admin: 'Admin' }

// Feste linke Seitenleiste (9.6); Werkstattname oben links führt zur Startseite (9.2).
// Es werden nur Bereiche angezeigt, die die Rolle nutzen darf (7.2).
function Seitenleiste({ nutzer }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const aktivWenn = (bedingung) => () => `seitenleiste__link${bedingung ? ' active' : ''}`
  return (
    <aside className="seitenleiste">
      <Link to="/" className="seitenleiste__start">Instrumenten&shy;werkstatt</Link>
      {/* Primäre Aktion, abgesetzt von der übrigen Navigation (9.2) */}
      <NavLink to="/neu" className="btn btn--primaer seitenleiste__aktion">Neuer Auftrag</NavLink>
      {/* Gliederung nach Tagesgeschäft und Verwaltung (9.2); ohne Verwaltung braucht es keine Überschrift */}
      <nav className="seitenleiste__nav" aria-label="Tagesgeschäft">
        {hatRolle('admin') && <span className="seitenleiste__titel">Tagesgeschäft</span>}
        {hatRolle('werkstattleiter') && <NavLink to="/" end className="seitenleiste__link">Übersicht</NavLink>}
        <NavLink to="/auftraege" className={aktivWenn(pathname === '/auftraege' || pathname.startsWith('/auftrag/'))}>Aufträge</NavLink>
        <NavLink to="/kunden" className="seitenleiste__link">Kunden</NavLink>
        {hatRolle('werkstattleiter') && <NavLink to="/abwesenheiten" className="seitenleiste__link">Abwesenheiten</NavLink>}
        {hatRolle('werkstattleiter') && <NavLink to="/auswertungen" className="seitenleiste__link">Auswertungen</NavLink>}
      </nav>
      {hatRolle('admin') && (
        <nav className="seitenleiste__nav seitenleiste__gruppe" aria-label="Verwaltung">
          <span className="seitenleiste__titel">Verwaltung</span>
          <NavLink to="/verwaltung/preisliste"
                   className={aktivWenn(pathname === '/verwaltung/preisliste' || pathname === '/verwaltung/vorgabewerte')}>
            Preisliste
          </NavLink>
          <NavLink to="/verwaltung/mitarbeiter" className="seitenleiste__link">Mitarbeiter</NavLink>
          <NavLink to="/verwaltung/einstellungen" className="seitenleiste__link">Einstellungen</NavLink>
          <span className="seitenleiste__titel seitenleiste__untertitel">Stammdaten</span>
          <NavLink to="/verwaltung/instrumentenklassen" className="seitenleiste__link seitenleiste__link--unter">Instrumentenklassen</NavLink>
          <NavLink to="/verwaltung/reparaturarten" className="seitenleiste__link seitenleiste__link--unter">Reparaturarten</NavLink>
        </nav>
      )}
      <div className="seitenleiste__nutzer">
        <strong>{nutzer.name}</strong>
        {ROLLEN[nutzer.systemrolle] ?? nutzer.systemrolle}
        <div>
          <button className="btn btn--sekundaer btn--klein" onClick={() => { abmelden(); navigate('/login') }}>
            Abmelden
          </button>
        </div>
      </div>
    </aside>
  )
}

export default function Intern() {
  const ort = useLocation()
  const [nutzer, setNutzer] = useState(angemeldeterNutzer())

  // Rolle frisch vom Backend holen, z. B. nach einer Rollenänderung durch den Admin
  useEffect(() => {
    if (angemeldeterNutzer()) nutzerAktualisieren().then(setNutzer).catch(() => {})
  }, []) // nur beim Start

  if (!nutzer) return <Navigate to="/login" state={{ zurueck: ort.pathname }} replace />
  return (
    <RueckmeldungBereich>
      <div className="layout">
        <Seitenleiste nutzer={nutzer} />
        <main className="inhalt"><Outlet /></main>
      </div>
    </RueckmeldungBereich>
  )
}
