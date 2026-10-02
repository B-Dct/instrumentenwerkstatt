// Seitenadressen der Anwendung (Daten-Router: nötig für die Rückfrage bei ungespeicherten Änderungen, 9.1/9.10)
import { createBrowserRouter, Navigate } from 'react-router'
import Intern from './Layout.jsx'
import AuftragDetail from './seiten/AuftragDetail.jsx'
import AuftragListe from './seiten/AuftragListe.jsx'
import AuftragNeu from './seiten/AuftragNeu.jsx'
import KundeDetail from './seiten/KundeDetail.jsx'
import Kunden from './seiten/Kunden.jsx'
import Login from './seiten/Login.jsx'
import Einstellungen from './seiten/verwaltung/Einstellungen.jsx'
import Instrumentenklassen from './seiten/verwaltung/Instrumentenklassen.jsx'
import Reparaturarten from './seiten/verwaltung/Reparaturarten.jsx'
import Vorgabewerte from './seiten/verwaltung/Vorgabewerte.jsx'
import Mitarbeiter from './seiten/verwaltung/Mitarbeiter.jsx'
import MitarbeiterDetail from './seiten/verwaltung/MitarbeiterDetail.jsx'
import NurRolle from './komponenten/NurRolle.jsx'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <Intern />,
    children: [
      { path: '/', element: <AuftragListe /> },
      { path: '/neu', element: <AuftragNeu /> },
      { path: '/auftrag/:id', element: <AuftragDetail /> },
      { path: '/kunden', element: <Kunden /> },
      { path: '/kunden/:id', element: <KundeDetail /> },
      // Verwaltung: nur Admin (7.2)
      { path: '/verwaltung/instrumentenklassen', element: <NurRolle rolle="admin"><Instrumentenklassen /></NurRolle> },
      { path: '/verwaltung/reparaturarten', element: <NurRolle rolle="admin"><Reparaturarten /></NurRolle> },
      { path: '/verwaltung/vorgabewerte', element: <NurRolle rolle="admin"><Vorgabewerte /></NurRolle> },
      { path: '/verwaltung/mitarbeiter', element: <NurRolle rolle="admin"><Mitarbeiter /></NurRolle> },
      { path: '/verwaltung/einstellungen', element: <NurRolle rolle="admin"><Einstellungen /></NurRolle> },
      { path: '/verwaltung/mitarbeiter/:id', element: <NurRolle rolle="admin"><MitarbeiterDetail /></NurRolle> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
