// Zugriff aufs Backend. Das Login-Token liegt im localStorage des Browsers
// (für den Prototyp ausreichend; für die finale Version neu bewerten).

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const TOKEN_KEY = 'werkstatt_token'
const NUTZER_KEY = 'werkstatt_nutzer'

export function angemeldeterNutzer() {
  const nutzer = localStorage.getItem(NUTZER_KEY)
  return localStorage.getItem(TOKEN_KEY) && nutzer ? JSON.parse(nutzer) : null
}

export function abmelden() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(NUTZER_KEY)
}

export class ApiFehler extends Error {
  constructor(status, meldung) {
    super(meldung)
    this.status = status
  }
}

// FastAPI liefert Fehler als Text oder (bei Eingabefehlern) als Liste
function fehlertext(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((f) => `${f.loc?.slice(1).join('.') || 'Eingabe'}: ${f.msg}`).join('; ')
  }
  return 'Unbekannter Fehler'
}

async function anfrage(pfad, { methode = 'GET', daten, formular } = {}) {
  const headers = {}
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.Authorization = `Bearer ${token}`
  let body
  if (formular) {
    body = new URLSearchParams(formular)
  } else if (daten !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(daten)
  }

  let antwort
  try {
    antwort = await fetch(API_URL + pfad, { method: methode, headers, body })
  } catch {
    throw new ApiFehler(0, `Backend nicht erreichbar (${API_URL}) – läuft es?`)
  }
  const inhalt = antwort.headers.get('content-type')?.includes('json') ? await antwort.json() : null
  if (!antwort.ok) {
    if (antwort.status === 401 && pfad !== '/auth/login') {
      // Token abgelaufen/ungültig → zurück zur Anmeldung
      abmelden()
      window.location.assign('/login')
    }
    throw new ApiFehler(antwort.status, fehlertext(inhalt?.detail))
  }
  return inhalt
}

export async function anmelden(email, passwort) {
  const antwort = await anfrage('/auth/login', { methode: 'POST', formular: { username: email, password: passwort } })
  localStorage.setItem(TOKEN_KEY, antwort.access_token)
  localStorage.setItem(NUTZER_KEY, JSON.stringify(antwort.mitarbeiter))
  return antwort.mitarbeiter
}

export const api = {
  auftraege: (filter = {}) => anfrage('/auftraege?' + new URLSearchParams(filter)),
  auftrag: (id) => anfrage(`/auftraege/${id}`),
  auftragAnlegen: (daten) => anfrage('/auftraege', { methode: 'POST', daten }),
  statusWechseln: (id, daten) => anfrage(`/auftraege/${id}/status`, { methode: 'POST', daten }),
  schaetzungKorrigieren: (id, daten) => anfrage(`/auftraege/${id}/schaetzung-korrektur`, { methode: 'POST', daten }),
  kunden: () => anfrage('/kunden'),
  instrumente: (kundeId) => anfrage('/instrumente?' + new URLSearchParams({ kunde_id: kundeId })),
  reparaturarten: () => anfrage('/reparaturarten'),
  auftragsstatus: () => anfrage('/auftragsstatus'),
  mitarbeiter: () => anfrage('/mitarbeiter'),
}

// Anzeige-Helfer
export const datum = (wert) => (wert ? new Date(wert).toLocaleDateString('de-DE') : '–')
export const zeit = (wert) => (wert ? new Date(wert).toLocaleString('de-DE') : '–')
export const stunden = (wert) => (wert == null ? '–' : `${wert.toLocaleString('de-DE')} Std.`)
export const euro = (wert) =>
  wert == null ? '–' : wert.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
