from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import schemas
from app.models import models
from app import database
from app.auth import get_current_user
from sqlalchemy import String, and_, cast, select
from sqlalchemy.orm import selectinload
from app.dependencies import templates

router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/classes", response_class=HTMLResponse)
async def view_schedule(
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Получаем расписание с явной загрузкой связанных данных
    schedules = await get_schedule(db, current_user)
    
    # Форматируем данные для шаблона с предварительной загрузкой
    formatted_schedules = []
    for schedule in schedules:
        # Явно загружаем связанные данные
        await db.refresh(schedule, ['subject'])
        await db.refresh(schedule.subject, ['groups', 'teacher'])
        await db.refresh(schedule.subject.teacher, ['user'])
        
        formatted_schedules.append({
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
            "subject": schedule.subject
        })
    
    return templates.TemplateResponse(
        "calendar/schedule.html",
        {
            "request": request,
            "schedules": formatted_schedules,
            "current_user": current_user
        }
    )

async def get_schedule(db: AsyncSession, current_user: models.User):
    if current_user.role == "student":
        result = await db.execute(
            select(models.User)
            .options(selectinload(models.User.student_profile))
            .where(models.User.id == current_user.id)
        )
        user = result.scalar()
        
        if not user.student_profile or not user.student_profile.group_id:
            raise HTTPException(status_code=403, detail="Student not in group")

        result = await db.execute(
            select(models.Schedule)
            .options(
                selectinload(models.Schedule.subject)
                .selectinload(models.Subject.groups),
                selectinload(models.Schedule.subject)
                .selectinload(models.Subject.teacher)
                .selectinload(models.Teacher.user)
            )
            .join(models.Subject)
            .join(models.group_subject)
            .join(models.Group)
            .where(models.Group.id == user.student_profile.group_id)
        )
        return result.scalars().all()
    
    else:
        # Для преподавателя
        result = await db.execute(
            select(models.Schedule)
            .options(
                selectinload(models.Schedule.subject)
                .selectinload(models.Subject.groups),
                selectinload(models.Schedule.subject)
                .selectinload(models.Subject.teacher)
                .selectinload(models.Teacher.user)
            )
            .join(models.Subject)
            .where(models.Subject.teacher_id == current_user.id)
        )
        return result.scalars().all()
    
@router.get("/schedule", response_model=list[schemas.ScheduleResponse])
async def get_schedule_api(
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "student":
        # Явная загрузка профиля студента
        result = await db.execute(
            select(models.User)
            .options(selectinload(models.User.student_profile))
            .where(models.User.id == current_user.id)
        )
        user = result.scalar()
        
        if not user.student_profile or not user.student_profile.group_id:
            raise HTTPException(status_code=403, detail="Student not in group")

        # Получаем расписание через связи
        schedule_result = await db.execute(
            select(models.Schedule)
            .join(models.Subject)
            .join(models.group_subject)
            .join(models.Group)
            .where(
                models.Group.id == user.student_profile.group_id,
                models.group_subject.c.subject_id == models.Subject.id
            )
        )
        return schedule_result.scalars().all()
    
    else:
        # Для преподавателя
        result = await db.execute(
            select(models.Schedule)
            .join(models.Subject)
            .where(models.Subject.teacher_id == current_user.id)
        )
        return result.scalars().all()
    
@router.get("/deadlines", response_class=HTMLResponse)
async def student_deadlines(
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "student":
        raise HTTPException(403, "Forbidden")

    # Получаем студента и его группу
    student = await db.execute(
        select(models.Student)
        .options(selectinload(models.Student.group))
        .where(models.Student.user_id == current_user.id)
    )
    student = student.scalar()
    
    if not student:
        raise HTTPException(404, "Student not found")

    # Получаем все задания для группы студента
    assignments = await db.execute(
        select(models.CourseMaterial)
        .options(
            selectinload(models.CourseMaterial.subject),
            selectinload(models.CourseMaterial.submissions)
        )
        .where(and_(
            models.CourseMaterial.group_id == student.group_id,
            cast(models.CourseMaterial.type, String) == "assignment",  # ✅ Исправлено
            models.CourseMaterial.deadline > datetime.now() - timedelta(days=7)
        ))
        .order_by(models.CourseMaterial.deadline.asc())
    )
    assignments = assignments.scalars().all()

    return templates.TemplateResponse(
        "assignments/deadlines.html",
        {
            "request": request,
            "assignments": assignments,
            "current_time": datetime.now(),
            "current_user": current_user
        }
    )
