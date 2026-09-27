import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
// Schriften lokal eingebunden (keine Anfrage an Google-Server)
import '@fontsource-variable/inter'
import '@fontsource-variable/fraunces'
import './styles/tokens.css'
import './styles/basis.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
