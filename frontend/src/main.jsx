import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
// Schriften lokal eingebunden (keine Anfrage an Google-Server)
import '@fontsource-variable/inter'
import '@fontsource-variable/fraunces'
import './styles/tokens.css'
import './styles/basis.css'
import { router } from './router.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
