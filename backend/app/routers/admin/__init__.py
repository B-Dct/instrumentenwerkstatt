"""Administrationsbereich (Datenmodell Abschnitt 7).

Alle Endpunkte unter /admin laufen durch `require_admin`. Neue Admin-Endpunkte
hier einhängen, dann greift die Berechtigungsprüfung automatisch mit.
"""

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.routers.admin import stammdaten, vorgabewerte

# Nur Systemrolle "admin" (Berechtigungsmatrix 7.2)
router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
router.include_router(stammdaten.router)
router.include_router(vorgabewerte.router)
