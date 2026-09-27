// Statusdarstellung nach Datenmodell 9.3: Farbe + Symbol + Text, nie Farbe allein.
// Farbe und Symbol kommen aus der Datenbank (auftragsstatus), siehe styles/tokens.css.

export function Status({ status }) {
  return (
    <span className="status" style={{ '--status-farbe': status.farbe }}>
      <span className="status__symbol" aria-hidden="true">{status.symbol}</span>
      {status.bezeichnung}
    </span>
  )
}

export function Ueberfaellig() {
  return (
    <span className="markierung markierung--ueberfaellig">
      <span aria-hidden="true">⚠</span> überfällig
    </span>
  )
}

export function HohePrioritaet() {
  return (
    <span className="markierung markierung--prioritaet">
      <span aria-hidden="true">⚑</span> hohe Priorität
    </span>
  )
}
