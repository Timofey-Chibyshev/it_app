from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models import models
from app.dependencies import templates
from app.auth import get_current_user
from app import database

router = APIRouter(
    prefix="/reports",
    tags=["reports"]
)

async def get_student_grades(db: AsyncSession, student_id: int):
    result = await db.execute(
        select(models.Subject.name, func.avg(models.AssignmentSubmission.grade).label('avg_grade'))
        .select_from(models.AssignmentSubmission)
        .join(models.CourseMaterial)
        .join(models.Subject)
        .where(and_(
            models.AssignmentSubmission.student_id == student_id,
            models.AssignmentSubmission.grade.isnot(None)
        ))
        .group_by(models.Subject.name)
    )
    return result.all()

async def get_teacher_report_data(db: AsyncSession, teacher_id: int):
    subjects = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.groups)
            .selectinload(models.Group.students)
            .selectinload(models.Student.user),
            selectinload(models.Subject.groups)
            .selectinload(models.Group.students)
            .selectinload(models.Student.submissions)
            .selectinload(models.AssignmentSubmission.material),
            selectinload(models.Subject.materials)
        )
        .where(models.Subject.teacher_id == teacher_id)
    )
    return subjects.scalars().all()
@router.get("/", response_class=HTMLResponse)
async def reports_main(
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "student":
        # Отчет для студента
        student = await db.execute(
            select(models.Student)
            .where(models.Student.user_id == current_user.id)
        )
        student = student.scalar()
        
        grades = await get_student_grades(db, student.id)
        return templates.TemplateResponse(
            "reports/student.html",
            {
                "request": request,
                "grades": grades,
                "current_user": current_user
            }
        )
    
    elif current_user.role == "teacher":
        # Отчет для преподавателя
        subjects = await get_teacher_report_data(db, current_user.id)
        return templates.TemplateResponse(
            "reports/teacher.html",
            {
                "request": request,
                "subjects": subjects,
                "current_user": current_user
            }
        )
    
    raise HTTPException(403, "Access denied")
