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
      <nav className="seitenleiste__nav" aria-label="Hauptnavigation">
        <NavLink to="/" className={aktivWenn(pathname === '/' || pathname.startsWith('/auftrag/'))}>Aufträge</NavLink>
        <NavLink to="/neu" className="seitenleiste__link">Neuer Auftrag</NavLink>
        <NavLink to="/kunden" className="seitenleiste__link">Kunden</NavLink>
        {hatRolle('werkstattleiter') && <NavLink to="/abwesenheiten" className="seitenleiste__link">Abwesenheiten</NavLink>}
      </nav>
      {hatRolle('admin') && (
        <nav className="seitenleiste__nav seitenleiste__gruppe" aria-label="Verwaltung">
          <span className="seitenleiste__titel">Verwaltung</span>
          <NavLink to="/verwaltung/instrumentenklassen" className="seitenleiste__link">Instrumentenklassen</NavLink>
          <NavLink to="/verwaltung/reparaturarten" className="seitenleiste__link">Reparaturarten</NavLink>
          <NavLink to="/verwaltung/vorgabewerte" className="seitenleiste__link">Vorgabewerte</NavLink>
          <NavLink to="/verwaltung/mitarbeiter" className="seitenleiste__link">Mitarbeiter</NavLink>
          <NavLink to="/verwaltung/einstellungen" className="seitenleiste__link">Einstellungen</NavLink>
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
