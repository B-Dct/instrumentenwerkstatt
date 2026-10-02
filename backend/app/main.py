from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import abwesenheiten, admin, auftraege, auswahllisten, auth, kunden
from app.speichern import konflikt_meldung

app = FastAPI(title="Werkstatt-Auftragsmanagement")

# Erlaubt dem Frontend in der lokalen Entwicklung Anfragen ans Backend – von jedem
# localhost-Port (Vite weicht z. B. auf 5174 aus, wenn 5173 belegt ist).
# TODO: Vor einem Betrieb außerhalb des lokalen Rechners auf die echte Frontend-Adresse beschränken.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def datenregel_verletzt(request: Request, fehler: IntegrityError) -> JSONResponse:
    """Sicherheitsnetz: Datenbankregel verletzt, ohne dass der Endpunkt sicher_speichern nutzt.
    Liefert 409 mit verständlicher Meldung statt 500. Die Sitzung dieser Anfrage wird danach
    ohnehin verworfen (get_db schließt sie)."""
    return JSONResponse(status_code=409, content={"detail": konflikt_meldung(fehler)})


app.include_router(auth.router)
app.include_router(abwesenheiten.router)
app.include_router(admin.router)
app.include_router(auftraege.router)
app.include_router(auswahllisten.router)
app.include_router(kunden.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "datenbank": "verbunden"}
