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
    <form onSubmit={absenden}>
      <h1>Anmelden</h1>
      <label>E-Mail <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus /></label>
      <label>Passwort <input type="password" value={passwort} onChange={(e) => setPasswort(e.target.value)} required /></label>
      <button disabled={laedt}>{laedt ? 'Anmelden …' : 'Anmelden'}</button>
      {fehler && <p className="fehler">{fehler}</p>}
    </form>
  )
}
