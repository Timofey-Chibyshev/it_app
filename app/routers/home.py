# app/routers/home.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models import models
from app.auth import templates
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Новая домашняя страница после авторизации
@router.get("/home", response_class=HTMLResponse)
async def home_page(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user or not current_user.is_active:
        return RedirectResponse("/auth/login", status_code=302)

    try:
        context = {
            "request": request,
            "current_user": current_user,
            "is_teacher": current_user.role.value == "teacher"  # Используем .value для enum
        }
        return templates.TemplateResponse("home.html", context)
    
    except Exception as e:
        logger.error(f"Home page error: {str(e)}")
        return RedirectResponse("/auth/login")

# Публичная главная страница
@router.get("/", response_class=HTMLResponse)
async def public_main_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})