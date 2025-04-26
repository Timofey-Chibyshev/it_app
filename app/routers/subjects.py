import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import schemas
from app.models import models
from app import database
from app.auth import get_current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/subjects", tags=["subjects"])

@router.get("/my", response_model=list[schemas.SubjectResponse])
async def get_my_subjects(
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "teacher":
        result = await db.execute(
            select(models.Subject)
            .join(models.Teacher)
            .options(selectinload(models.Subject.groups))
            .where(models.Teacher.user_id == current_user.id)
        )
        subjects = result.scalars().all()
        return subjects
    else:
        result = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
            .options(
                selectinload(models.Student.group)
                .selectinload(models.Group.subjects)
                .selectinload(models.Subject.groups)
            )
        )
        student = result.scalar()
        
        if not student or not student.group:
            raise HTTPException(status_code=403, detail="Student is not assigned to a group")

        return student.group.subjects


@router.post("/", response_model=schemas.SubjectResponse)
async def create_subject(
    subject_data: schemas.SubjectCreate,  # Переименовано для ясности
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create subjects")

    # Создаем предмет без явного указания teacher_id
    db_subject = models.Subject(
        **subject_data.dict(exclude={"teacher_id"}),  # Исключаем teacher_id из запроса
        teacher_id=current_user.id  # Берем ID из текущего пользователя
    )
    
    db.add(db_subject)
    await db.commit()
    await db.refresh(db_subject)
    return db_subject
