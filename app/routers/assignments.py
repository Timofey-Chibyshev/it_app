import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))  # Добавляем корень проекта в PYTHONPATH

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas import schemas
from app.models import models
from app import database
from app.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("/submit", response_model=schemas.SubmissionResponse)
async def submit_assignment(
    submission: schemas.SubmissionCreate,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit assignments")

    # Получаем профиль студента
    student = await db.execute(
        select(models.Student)
        .where(models.Student.user_id == current_user.id)
    )
    student = student.scalar()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Проверяем материал
    material = await db.get(models.CourseMaterial, submission.material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
        
    if material.deadline and material.deadline < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Deadline has passed")

    # Создаем submission
    db_submission = models.AssignmentSubmission(
        file_path=submission.file_path,
        material_id=submission.material_id,
        student_id=student.id  # Используем ID из таблицы students
    )

    db.add(db_submission)
    await db.commit()
    await db.refresh(db_submission)
    return db_submission


@router.patch("/{submission_id}", response_model=schemas.SubmissionResponse)
async def grade_assignment(
    submission_id: int,
    grade_data: schemas.SubmissionGrade,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can grade assignments")

    # Получаем submission с явной проверкой
    result = await db.execute(
        select(models.AssignmentSubmission)
        .where(models.AssignmentSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    
    if submission is None:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")

    # Валидация данных
    if grade_data.status not in ['graded', 'rejected']:
        raise HTTPException(status_code=400, detail="Invalid status value")

    # Обновление полей
    try:
        submission.grade = grade_data.grade
        submission.status = grade_data.status
        submission.feedback = grade_data.feedback
        await db.commit()
        await db.refresh(submission)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return submission