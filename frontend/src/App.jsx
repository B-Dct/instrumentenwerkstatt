import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import { abmelden, angemeldeterNutzer } from './api.js'
import AuftragDetail from './seiten/AuftragDetail.jsx'
import AuftragListe from './seiten/AuftragListe.jsx'
import AuftragNeu from './seiten/AuftragNeu.jsx'
import Login from './seiten/Login.jsx'

function NurAngemeldet({ children }) {
  const ort = useLocation()
  return angemeldeterNutzer() ? children : <Navigate to="/login" state={{ zurueck: ort.pathname }} replace />
}

function Kopfzeile() {
  const nutzer = angemeldeterNutzer()
  const navigate = useNavigate()
  if (!nutzer) return null
  return (
    <header>
      <Link to="/">Aufträge</Link> | <Link to="/neu">Neuer Auftrag</Link>
      <span className="rechts">
        {nutzer.name} ({nutzer.systemrolle}){' '}
        <button onClick={() => { abmelden(); navigate('/login') }}>Abmelden</button>
      </span>
    </header>
  )
}

export default function App() {
  return (
    <>
      <p className="hinweis">Klick-Prototyp – nur funktional, ohne Gestaltung</p>
      <Kopfzeile />
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<NurAngemeldet><AuftragListe /></NurAngemeldet>} />
          <Route path="/neu" element={<NurAngemeldet><AuftragNeu /></NurAngemeldet>} />
          <Route path="/auftrag/:id" element={<NurAngemeldet><AuftragDetail /></NurAngemeldet>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}
