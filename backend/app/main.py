from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.routers import admin, auftraege, auswahllisten, auth

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

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(auftraege.router)
app.include_router(auswahllisten.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "datenbank": "verbunden"}
