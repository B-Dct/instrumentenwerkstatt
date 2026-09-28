// Seite nur für eine Mindestrolle (7.2). Das Backend prüft unabhängig davon.
import { hatRolle } from '../api.js'

export default function NurRolle({ rolle, children }) {
  if (!hatRolle(rolle)) {
    return <p className="meldung meldung--fehler">Für diesen Bereich fehlt die Berechtigung.</p>
  }
  return children
}
