from datetime import timedelta
from typing import Annotated, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
    Form,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import ValidationError
import logging

from app.database import get_db
from app.auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    templates,
)
from app.schemas.schemas import RefreshRequest, TokenPair, UserCreate, UserResponse
from app.models.models import User, Student, Teacher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------
# Web Interface Handlers
# ---------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": error,
            "form_data": {}  # Пустой словарь для новых сессий
        }
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "error": error,
            "form_data": {}  # Добавляем пустые данные
        }
    )

@router.post("/login-form", response_class=HTMLResponse)
async def web_login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")

    user = await authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Неверный email или пароль",
                "form_data": form_data  # Передаем данные формы обратно
            }
        )

    # Создаем оба токена
    access_token = create_access_token(
        {"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(
        {"sub": user.email},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    response = RedirectResponse("/home", status_code=302)

    # Устанавливаем куки
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        secure=True,
        samesite="Lax"
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        secure=True,
        samesite="Lax"
    )

    return response


@router.post("/register-form", response_class=HTMLResponse)
async def web_register(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        first_name: str = Form(...),
        last_name: str = Form(...),
        role: str = Form(...),
        group: Optional[str] = Form(None),  # Добавляем поле группы
        db: AsyncSession = Depends(get_db)
):
    role_map = {
        "Студент": "student",
        "Преподаватель": "teacher"
    }
    role_value = role_map.get(role, role)
    form_data = await request.form()  # Получаем все данные формы

    try:
        # Проверка группы для студентов
        if role_value == "student" and not group:
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "request": request,
                    "error": "Для студентов необходимо указать номер группы",
                    "form_data": dict(form_data)
                }
            )

        # Валидация и создание пользователя
        user_data = UserCreate(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role_value,
            patronymic=None
        )

        existing_user = await db.execute(
            select(User).where(User.email == user_data.email))
        if existing_user.scalar():
            return templates.TemplateResponse(
                "auth/register.html",
                {
                    "request": request,
                    "error": "Email уже зарегистрирован",
                    "form_data": dict(form_data)
                }
            )

        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            is_active=True
        )

        db.add(db_user)
        await db.flush()

        # Создаем профиль с учетом группы
        if db_user.role == "teacher":
            teacher = Teacher(user_id=db_user.id, position="Преподаватель")
            db.add(teacher)
        elif db_user.role == "student":
            # Добавляем проверку и сохранение группы
            if not group:
                await db.rollback()
                return templates.TemplateResponse(
                    "auth/register.html",
                    {
                        "request": request,
                        "error": "Укажите номер группы",
                        "form_data": dict(form_data)
                    }
                )

            student = Student(user_id=db_user.id, group=group)  # Используем поле group
            db.add(student)

        await db.commit()
        await db.refresh(db_user)

        return RedirectResponse("/auth/login", status_code=302)

    except ValidationError as e:
        await db.rollback()
        error_msg = ", ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": f"Ошибка валидации: {error_msg}",
                "form_data": dict(form_data)
            }
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Registration error: {str(e)}")
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": "Ошибка регистрации",
                "form_data": dict(form_data)
            }
        )


# ---------------------------
# API Endpoints
# ---------------------------

@router.post("/login", response_model=TokenPair)
async def api_login(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль"
        )

    return {
        "access_token": create_access_token(
            {"sub": user.email},
            timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        ),
        "refresh_token": create_refresh_token(
            {"sub": user.email},
            timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        ),
        "token_type": "bearer"
    }


@router.post("/registration", response_model=UserResponse)
async def api_register(
        user: UserCreate,
        db: AsyncSession = Depends(get_db)
):
    existing_user = await db.execute(
        select(User).where(User.email == user.email))
    if existing_user.scalar():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email уже зарегистрирован"
        )

    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        patronymic=user.patronymic,
        role=user.role,
        is_active=True
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return UserResponse.model_validate(db_user)


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(
        request: RefreshRequest,
        db: AsyncSession = Depends(get_db)
):
    email = verify_refresh_token(request.refresh_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный refresh токен"
        )

    return {
        "access_token": create_access_token(
            {"sub": email},
            timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        ),
        "refresh_token": create_refresh_token(
            {"sub": email},
            timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        ),
        "token_type": "bearer"
    }


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
