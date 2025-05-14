from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload, joinedload

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
        select(
            models.Subject.id.label("subject_id"),
            models.Subject.name,
            func.avg(models.AssignmentSubmission.grade).label('avg_grade')
        )
        .select_from(models.AssignmentSubmission)
        .join(models.CourseMaterial, models.AssignmentSubmission.material_id == models.CourseMaterial.id)
        .join(models.Subject, models.CourseMaterial.subject_id == models.Subject.id)
        .where(and_(
            models.AssignmentSubmission.student_id == student_id,
            models.AssignmentSubmission.grade.isnot(None)
        ))
        .group_by(models.Subject.id)
    )
    return [{"id": r.subject_id, "name": r.name, "avg_grade": r.avg_grade} for r in result.all()]

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
            .joinedload(models.AssignmentSubmission.material),
            selectinload(models.Subject.materials)
        )
        .where(models.Subject.teacher_id == teacher_id)
    )
    return subjects.scalars().all()

@router.get("/", response_class=HTMLResponse, name="reports_main")
async def reports_main(
    request: Request,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "student":
        student = await db.execute(
            select(models.Student)
            .options(
                selectinload(models.Student.group)
            )
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

async def get_student_subject_grades(db: AsyncSession, student_id: int, subject_id: int):
    result = await db.execute(
        select(
            models.CourseMaterial.title,
            models.AssignmentSubmission.grade,
            models.AssignmentSubmission.feedback,
            models.AssignmentSubmission.submission_date,
            models.AssignmentSubmission.status
        )
        .select_from(models.AssignmentSubmission)
        .join(models.CourseMaterial)
        .where(and_(
            models.AssignmentSubmission.student_id == student_id,
            models.CourseMaterial.subject_id == subject_id
        ))
        .order_by(models.AssignmentSubmission.submission_date.desc())
    )
    return result.all()

@router.get("/student/subject/{subject_id}", response_class=HTMLResponse, name="student_subject_report")
async def student_subject_report(
    request: Request,
    subject_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Получаем студента с группой и предметами
    student = await db.execute(
        select(models.Student)
        .options(
            selectinload(models.Student.group)
            .selectinload(models.Group.subjects)
        )
        .where(models.Student.user_id == current_user.id)
    )
    student = student.scalar()
    
    subject = await db.get(models.Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    student_group_ids = [g.id for g in student.group.subjects]
    if subject.id not in student_group_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    
    grades = await get_student_subject_grades(db, student.id, subject_id)
    
    return templates.TemplateResponse(
        "reports/student_subject_details.html",
        {
            "request": request,
            "subject": subject,
            "grades": grades,
            "current_user": current_user
        }
    )

@router.get(
    "/teacher/student/{student_id}/subject/{subject_id}", 
    response_class=HTMLResponse,
    name="teacher_student_report"
)
async def teacher_student_subject_report(
    request: Request,
    student_id: int,
    subject_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Проверка принадлежности предмета
    subject = await db.execute(
        select(models.Subject)
        .where(and_(
            models.Subject.id == subject_id,
            models.Subject.teacher_id == current_user.id
        ))
    )
    subject = subject.scalar()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # Получаем данные студента
    student = await db.execute(
        select(models.Student)
        .options(
            selectinload(models.Student.user),
            selectinload(models.Student.submissions)
            .joinedload(models.AssignmentSubmission.material)
        )
        .where(models.Student.id == student_id)
    )
    student = student.scalar()
    
    # Получаем все оценки
    submissions = await db.execute(
        select(models.AssignmentSubmission)
        .options(joinedload(models.AssignmentSubmission.material))
        .join(models.CourseMaterial)
        .where(and_(
            models.AssignmentSubmission.student_id == student_id,
            models.CourseMaterial.subject_id == subject_id
        ))
        .order_by(models.CourseMaterial.deadline.asc())
    )
    submissions = submissions.unique().scalars().all()
    
    return templates.TemplateResponse(
        "reports/teacher_student_details.html",
        {
            "request": request,
            "student": student,
            "subject": subject,
            "submissions": submissions,
            "current_user": current_user
        }
    )