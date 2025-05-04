from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models import models
from app.auth import templates

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Проверка авторизации и активности
    if not current_user or not current_user.is_active:
        return RedirectResponse("/auth/login")

    # Подготовка контекста
    context = {
        "request": request,
        "current_user": current_user,
        "is_teacher": current_user.role == "teacher"
    }

    return templates.TemplateResponse("home.html", context)