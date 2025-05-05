from fastapi import FastAPI
from app.routers import (
    auth,
    users,
    groups,
    subjects,
    materials,
    assignments,
    calendar,
home
)
from app.database import engine, Base
from fastapi.staticfiles import StaticFiles
from app.dependencies import templates  # Измененный импорт

app = FastAPI()

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Убрали инициализацию шаблонов здесь
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
