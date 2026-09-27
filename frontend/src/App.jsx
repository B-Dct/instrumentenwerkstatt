import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router'
import { abmelden, angemeldeterNutzer } from './api.js'
import AuftragDetail from './seiten/AuftragDetail.jsx'
import AuftragListe from './seiten/AuftragListe.jsx'
import AuftragNeu from './seiten/AuftragNeu.jsx'
import Login from './seiten/Login.jsx'

const ROLLEN = { mitarbeiter: 'Mitarbeiter', werkstattleiter: 'Werkstattleitung', admin: 'Admin' }

// Feste linke Seitenleiste (9.6); Werkstattname oben links führt zur Startseite (9.2)
function Seitenleiste() {
  const nutzer = angemeldeterNutzer()
  const navigate = useNavigate()
  // Liste und Auftragsdetails gehören beide zum Bereich "Aufträge"
  const { pathname } = useLocation()
  const imAuftragsbereich = pathname === '/' || pathname.startsWith('/auftrag/')
  return (
    <aside className="seitenleiste">
      <Link to="/" className="seitenleiste__start">Instrumenten&shy;werkstatt</Link>
      <nav className="seitenleiste__nav">
        <NavLink to="/" className={() => `seitenleiste__link${imAuftragsbereich ? ' active' : ''}`}>Aufträge</NavLink>
        <NavLink to="/neu" className="seitenleiste__link">Neuer Auftrag</NavLink>
      </nav>
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

function Intern({ children }) {
  const ort = useLocation()
  if (!angemeldeterNutzer()) return <Navigate to="/login" state={{ zurueck: ort.pathname }} replace />
  return (
    <div className="layout">
      <Seitenleiste />
      <main className="inhalt">{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Intern><AuftragListe /></Intern>} />
      <Route path="/neu" element={<Intern><AuftragNeu /></Intern>} />
      <Route path="/auftrag/:id" element={<Intern><AuftragDetail /></Intern>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
