"""Administrationsbereich (Datenmodell Abschnitt 7).

Alle Endpunkte unter /admin laufen durch `require_admin`. Neue Admin-Endpunkte
hier einhängen, dann greift die Berechtigungsprüfung automatisch mit.
"""

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.routers.admin import vorgabewerte

# TODO: Sobald Login/Rollen implementiert sind (siehe ARCHITECTURE.md, Abschnitt 4
# "Berechtigungskonzept") – require_admin beschränkt dann den Zugriff auf Systemrolle
# "admin". Derzeit sind alle Endpunkte unter /admin UNGESCHÜTZT.
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
router.include_router(vorgabewerte.router)
