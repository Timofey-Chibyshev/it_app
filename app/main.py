from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.dependencies import templates  # Должен быть первым импортом!
from app.routers import (
    auth, users, groups,
    subjects, materials,
    assignments, calendar,
    home
)

from fastapi.staticfiles import StaticFiles


app = FastAPI()

# Важно: монтирование статики после импорта dependencies
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(home.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(subjects.router)
app.include_router(materials.router)
app.include_router(assignments.router)
app.include_router(calendar.router)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        