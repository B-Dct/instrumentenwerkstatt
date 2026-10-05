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
  constructor(status, meldung, felder = {}) {
    super(meldung)
    this.status = status
    this.felder = felder // Feldname → Fehlermeldung (für Inline-Validierung, 9.1)
  }
}

// Übersetzt die englischen Standardmeldungen der Eingabeprüfung ins Deutsche
function feldmeldung(f) {
  const ctx = f.ctx ?? {}
  switch (f.type) {
    case 'missing': return 'Pflichtfeld'
    case 'string_too_short': return 'Pflichtfeld'
    case 'string_too_long': return `Höchstens ${ctx.max_length} Zeichen`
    case 'greater_than': return `Muss größer als ${ctx.gt} sein`
    case 'greater_than_equal': return `Mindestens ${ctx.ge}`
    case 'less_than_equal': return `Höchstens ${ctx.le}`
    case 'decimal_max_places': return `Höchstens ${ctx.decimal_places} Nachkommastellen`
    case 'value_error': return f.msg.includes('email') ? 'Keine gültige E-Mail-Adresse' : f.msg
    case 'uuid_type': case 'uuid_parsing': return 'Bitte auswählen'
    case 'decimal_type': case 'decimal_parsing': case 'int_type': case 'int_parsing': return 'Bitte eine Zahl eingeben'
    default: return f.msg
  }
}

function fehlerJeFeld(detail) {
  if (!Array.isArray(detail)) return {}
  return Object.fromEntries(detail.filter((f) => f.loc?.length > 1).map((f) => [f.loc[f.loc.length - 1], feldmeldung(f)]))
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
    const felder = fehlerJeFeld(inhalt?.detail)
    const meldung = Object.keys(felder).length ? 'Bitte die markierten Felder prüfen' : fehlertext(inhalt?.detail)
    throw new ApiFehler(antwort.status, meldung, felder)
  }
  return inhalt
}

// Rolle/Name frisch vom Backend holen (z. B. nach Rollenänderung durch den Admin)
export async function nutzerAktualisieren() {
  const nutzer = await anfrage('/auth/ich')
  localStorage.setItem(NUTZER_KEY, JSON.stringify(nutzer))
  return nutzer
}

// Rollen sind kumulativ: admin ⊇ werkstattleiter ⊇ mitarbeiter (7.1)
const RANG = { mitarbeiter: 1, werkstattleiter: 2, admin: 3 }
export const hatRolle = (mindestens) => RANG[angemeldeterNutzer()?.systemrolle] >= RANG[mindestens]

export async function anmelden(email, passwort) {
  const antwort = await anfrage('/auth/login', { methode: 'POST', formular: { username: email, password: passwort } })
  localStorage.setItem(TOKEN_KEY, antwort.access_token)
  localStorage.setItem(NUTZER_KEY, JSON.stringify(antwort.mitarbeiter))
  return antwort.mitarbeiter
}

// Alle Einträge einer seitenweisen Liste (9.11) nacheinander holen – nur für Auswahlfelder,
// die wirklich jeden Eintrag brauchen (z. B. auch archivierte Stammdaten in der Verwaltung)
export async function alleEintraege(laden, filter = {}) {
  const eintraege = []
  for (let seite = 1; ; seite += 1) {
    const daten = await laden({ ...filter, seite, seitengroesse: 100 })
    eintraege.push(...daten.eintraege)
    if (eintraege.length >= daten.treffer || daten.eintraege.length === 0) return eintraege
  }
}

export const api = {
  dashboard: () => anfrage('/dashboard'),
  auswertungen: (parameter = {}) => anfrage('/auswertungen?' + new URLSearchParams(parameter)),
  auftraege: (filter = {}) => anfrage('/auftraege?' + new URLSearchParams(filter)),
  auftrag: (id) => anfrage(`/auftraege/${id}`),
  auftragAnlegen: (daten) => anfrage('/auftraege', { methode: 'POST', daten }),
  auftragAendern: (id, daten) => anfrage(`/auftraege/${id}`, { methode: 'PATCH', daten }),
  statusWechseln: (id, daten) => anfrage(`/auftraege/${id}/status`, { methode: 'POST', daten }),
  schaetzungKorrigieren: (id, daten) => anfrage(`/auftraege/${id}/schaetzung-korrektur`, { methode: 'POST', daten }),
  terminKorrigieren: (id, daten) => anfrage(`/auftraege/${id}/termin-korrektur`, { methode: 'POST', daten }),
  kunden: (filter = {}) => anfrage('/kunden?' + new URLSearchParams(filter)),
  kunde: (id) => anfrage(`/kunden/${id}`),
  kundeAnlegen: (daten) => anfrage('/kunden', { methode: 'POST', daten }),
  kundeAendern: (id, daten) => anfrage(`/kunden/${id}`, { methode: 'PATCH', daten }),
  kundeArchivieren: (id) => anfrage(`/kunden/${id}/archivieren`, { methode: 'POST' }),
  kundeReaktivieren: (id) => anfrage(`/kunden/${id}/reaktivieren`, { methode: 'POST' }),
  instrumente: (kundeId) => anfrage('/instrumente?' + new URLSearchParams({ kunde_id: kundeId })),
  instrumentAnlegen: (daten) => anfrage('/instrumente', { methode: 'POST', daten }),
  instrumentAendern: (id, daten) => anfrage(`/instrumente/${id}`, { methode: 'PATCH', daten }),
  instrumentArchivieren: (id) => anfrage(`/instrumente/${id}/archivieren`, { methode: 'POST' }),
  instrumentReaktivieren: (id) => anfrage(`/instrumente/${id}/reaktivieren`, { methode: 'POST' }),
  instrumentenklassen: () => anfrage('/instrumentenklassen'),
  // Je Instrumentenklasse ihre aktiven Ausführungen (2.4b): { klasseId: [{ id, bezeichnung, ist_standard }, …] }
  klassenAusfuehrungen: () => anfrage('/instrumentenklassen/ausfuehrungen'),
  // Abwesenheiten (nur Werkstattleitung/Admin)
  abwesenheiten: (filter = {}) => anfrage('/abwesenheiten?' + new URLSearchParams(filter)),
  abwesenheitenRaster: (parameter) => anfrage('/abwesenheiten/raster?' + new URLSearchParams(parameter)),
  abwesenheitAnlegen: (daten) => anfrage('/abwesenheiten', { methode: 'POST', daten }),
  abwesenheitAendern: (id, daten) => anfrage(`/abwesenheiten/${id}`, { methode: 'PATCH', daten }),
  abwesenheitStornieren: (id) => anfrage(`/abwesenheiten/${id}/stornieren`, { methode: 'POST' }),
  abwesenheitWiederherstellen: (id) => anfrage(`/abwesenheiten/${id}/wiederherstellen`, { methode: 'POST' }),
  // Verwaltung (nur Admin)
  admin: {
    einstellungen: () => anfrage('/admin/einstellungen'),
    feiertage: () => anfrage('/admin/feiertage'),
    feiertageErzeugen: (jahr) => anfrage('/admin/feiertage', { methode: 'POST', daten: { jahr } }),
    einstellungSetzen: (schluessel, wert) => anfrage(`/admin/einstellungen/${schluessel}`, { methode: 'PUT', daten: { wert } }),
    klassen: (filter = {}) => anfrage('/admin/instrumentenklassen?' + new URLSearchParams(filter)),
    klasseAnlegen: (daten) => anfrage('/admin/instrumentenklassen', { methode: 'POST', daten }),
    klasseAendern: (id, daten) => anfrage(`/admin/instrumentenklassen/${id}`, { methode: 'PATCH', daten }),
    klasseArchivieren: (id) => anfrage(`/admin/instrumentenklassen/${id}/archivieren`, { methode: 'POST' }),
    klasseReaktivieren: (id) => anfrage(`/admin/instrumentenklassen/${id}/reaktivieren`, { methode: 'POST' }),
    arten: (filter = {}) => anfrage('/admin/reparaturarten?' + new URLSearchParams(filter)),
    artAnlegen: (daten) => anfrage('/admin/reparaturarten', { methode: 'POST', daten }),
    artAendern: (id, daten) => anfrage(`/admin/reparaturarten/${id}`, { methode: 'PATCH', daten }),
    artArchivieren: (id) => anfrage(`/admin/reparaturarten/${id}/archivieren`, { methode: 'POST' }),
    artReaktivieren: (id) => anfrage(`/admin/reparaturarten/${id}/reaktivieren`, { methode: 'POST' }),
    ausfuehrungen: (filter = {}) => anfrage('/admin/ausfuehrungen?' + new URLSearchParams(filter)),
    ausfuehrungAnlegen: (daten) => anfrage('/admin/ausfuehrungen', { methode: 'POST', daten }),
    ausfuehrungAendern: (id, daten) => anfrage(`/admin/ausfuehrungen/${id}`, { methode: 'PATCH', daten }),
    ausfuehrungArchivieren: (id) => anfrage(`/admin/ausfuehrungen/${id}/archivieren`, { methode: 'POST' }),
    ausfuehrungReaktivieren: (id) => anfrage(`/admin/ausfuehrungen/${id}/reaktivieren`, { methode: 'POST' }),
    vorgabewerte: (filter = {}) => anfrage('/admin/vorgabewerte?' + new URLSearchParams(filter)),
    vorgabewertAnlegen: (daten) => anfrage('/admin/vorgabewerte', { methode: 'POST', daten }),
    vorgabewertAendern: (id, daten) => anfrage(`/admin/vorgabewerte/${id}`, { methode: 'PATCH', daten }),
    mitarbeiterListe: (parameter = {}) => anfrage('/admin/mitarbeiter?' + new URLSearchParams(parameter)),
    mitarbeiter: (id) => anfrage(`/admin/mitarbeiter/${id}`),
    mitarbeiterDeaktivieren: (id) => anfrage(`/admin/mitarbeiter/${id}/deaktivieren`, { methode: 'POST' }),
    mitarbeiterAktivieren: (id) => anfrage(`/admin/mitarbeiter/${id}/aktivieren`, { methode: 'POST' }),
    systemrolleAendern: (id, systemrolle) => anfrage(`/admin/mitarbeiter/${id}/systemrolle`, { methode: 'PATCH', daten: { systemrolle } }),
    wochenstunden: (id) => anfrage(`/admin/mitarbeiter/${id}/wochenstunden`),
    wochenstundenFestlegen: (id, daten) => anfrage(`/admin/mitarbeiter/${id}/wochenstunden`, { methode: 'POST', daten }),
    vorgabewertArchivieren: (id) => anfrage(`/admin/vorgabewerte/${id}/archivieren`, { methode: 'POST' }),
    vorgabewertReaktivieren: (id) => anfrage(`/admin/vorgabewerte/${id}/reaktivieren`, { methode: 'POST' }),
  },
  reparaturarten: () => anfrage('/reparaturarten'),
  // Ausführungen der Instrumentenklasse mit ihrem Richtpreis für die Reparaturart (2.6a); weniger als zwei = keine Auswahl nötig
  ausfuehrungen: (parameter) => anfrage('/ausfuehrungen?' + new URLSearchParams(parameter)),
  auftragsstatus: () => anfrage('/auftragsstatus'),
  mitarbeiter: () => anfrage('/mitarbeiter'),
}

// Anzeige-Helfer – Datumsformat einheitlich TT.MM.JJJJ (Design-System 9.6)
const DATUM = { day: '2-digit', month: '2-digit', year: 'numeric' }
export const datum = (wert) => (wert ? new Date(wert).toLocaleDateString('de-DE', DATUM) : '–')
export const zeit = (wert) =>
  wert ? new Date(wert).toLocaleString('de-DE', { ...DATUM, hour: '2-digit', minute: '2-digit' }) : '–'
export const zahl = (wert) => (wert == null ? '–' : wert.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
export const stunden = (wert) => (wert == null ? '–' : `${zahl(wert)} Std.`)
export const euro = (wert) =>
  wert == null ? '–' : wert.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
