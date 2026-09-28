// Seitenadressen der Anwendung (Daten-Router: nötig für die Rückfrage bei ungespeicherten Änderungen, 9.1/9.10)
import { createBrowserRouter, Navigate } from 'react-router'
import Intern from './Layout.jsx'
import AuftragDetail from './seiten/AuftragDetail.jsx'
import AuftragListe from './seiten/AuftragListe.jsx'
import AuftragNeu from './seiten/AuftragNeu.jsx'
import KundeDetail from './seiten/KundeDetail.jsx'
import Kunden from './seiten/Kunden.jsx'
import Login from './seiten/Login.jsx'

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
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
