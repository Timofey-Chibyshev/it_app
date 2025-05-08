import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import schemas
from app.models import models
from app.database import get_db
from sqlalchemy.orm import selectinload
from sqlalchemy import select

router = APIRouter(prefix="/groups", tags=["groups"])

@router.get("/{group_id}", response_model=schemas.GroupResponse)
async def get_group(
    group_id: int,
    db: AsyncSession = Depends(get_db)
):
    # Получаем группу с загруженными студентами
    result = await db.execute(
        select(models.Group)
        .options(selectinload(models.Group.students))
        .where(models.Group.id == group_id)
    )
    group = result.scalar()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Преобразуем объекты Student в их ID
    return {
        "id": group.id,
        "number": group.number,
        "students": [student.user_id for student in group.students]  # Используем user_id
    }