from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.schemas import UserResponse  # Изменяем импорт
from app.models.models import User as DBUser
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserResponse)  # Используем правильную схему
async def read_users_me(
    current_user: DBUser = Depends(get_current_user)  # Используем SQLAlchemy модель
):
    return UserResponse.model_validate(current_user)  # Конвертируем в Pydantic схему