import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { anmelden } from '../api.js'

export default function Login() {
  const [email, setEmail] = useState('')
  const [passwort, setPasswort] = useState('')
  const [fehler, setFehler] = useState(null)
  const [laedt, setLaedt] = useState(false)
  const navigate = useNavigate()
  const zurueck = useLocation().state?.zurueck ?? '/'

  async function absenden(e) {
    e.preventDefault()
    setFehler(null)
    setLaedt(true)
    try {
      await anmelden(email, passwort)
      navigate(zurueck, { replace: true })
    } catch (err) {
      setFehler(err.message)
    } finally {
      setLaedt(false)
    }
  }

  return (
    <main className="login">
      <h1>Instrumenten&shy;werkstatt</h1>
      <p className="leise">Anmeldung für Mitarbeiter</p>
      <form onSubmit={absenden}>
        <label className="feld">
          <span>E-Mail</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        <label className="feld">
          <span>Passwort</span>
          <input type="password" value={passwort} onChange={(e) => setPasswort(e.target.value)} required />
        </label>
        <button className="btn btn--primaer" disabled={laedt}>{laedt ? 'Anmelden …' : 'Anmelden'}</button>
        {fehler && <p className="meldung meldung--fehler" role="alert">{fehler}</p>}
      </form>
    </main>
  )
}
