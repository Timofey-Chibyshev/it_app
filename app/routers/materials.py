import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import schemas
from app.models import models
from app import database
from app.auth import get_current_user
import shutil
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/materials", tags=["materials"])

@router.post("/", response_model=schemas.MaterialResponse)
async def upload_material(
    title: str = Form(...),
    description: str = Form(None),
    type: str = Form(...),
    deadline: datetime = Form(None),
    group_id: int = Form(...),
    subject_id: int = Form(...),  
    file: UploadFile = File(...),
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can upload materials")

    # Проверка прав преподавателя на предмет
    subject = await db.get(models.Subject, subject_id)
    if not subject or subject.teacher.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this subject")

    # Сохранение файла
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Создание материала
    db_material = models.CourseMaterial(
        title=title,
        description=description,
        type=type,
        deadline=deadline,
        group_id=group_id,
        subject_id=subject_id,  # Добавляем связь с предметом
        file_path=file_path
    )

    db.add(db_material)
    await db.commit()
    await db.refresh(db_material)
    return db_material


@router.get("/{subject_id}", response_model=List[schemas.MaterialResponse])
async def get_subject_materials(
    subject_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Загрузка предмета с материалами
    subject = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups),
            selectinload(models.Subject.materials)
        )
        .where(models.Subject.id == subject_id)
    )
    subject = subject.scalar()
    
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Для преподавателей: проверка прав доступа
    if current_user.role == "teacher":
        teacher = await db.execute(
            select(models.Teacher)
            .where(models.Teacher.user_id == current_user.id)
        )
        teacher = teacher.scalar()
        if not teacher or subject.teacher_id != teacher.id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Для студентов: проверка группы
    if current_user.role == "student":
        student = await db.execute(
            select(models.Student)
            .options(selectinload(models.Student.group))
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        
        if not student or not student.group:
            raise HTTPException(status_code=403, detail="Student not in group")
            
        if student.group.id not in {g.id for g in subject.groups}:
            raise HTTPException(status_code=403, detail="Access denied")

    # Фильтрация материалов по группе для студентов
    if current_user.role == "student":
        materials = [m for m in subject.materials if m.group_id == student.group.id]
    else:
        materials = subject.materials

    return materials