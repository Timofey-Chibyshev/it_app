from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.models import Subject, CourseMaterial, Student, Group, User
from app.schemas.schemas import SubjectStudentView
from app.database import get_db
from app.auth import get_current_active_user

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/test-view/{subject_id}",
            response_model=SubjectStudentView,
            summary="Тестовый просмотр предмета (для студентов)",
            description="Возвращает полную информацию о предмете для студента")
async def test_student_subject_view(
        subject_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    # Проверка роли пользователя
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для студентов"
        )

    # Получаем информацию о студенте и его группе
    student = await db.execute(
        select(Student)
        .where(Student.user_id == current_user.id)
    )
    student = student.scalar_one_or_none()

    if not student or not student.group_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Студент не привязан к группе"
        )

    # Проверяем доступ к предмету
    subject_query = await db.execute(
        select(Subject)
        .join(Group.subjects)
        .where(and_(
            Subject.id == subject_id,
            Group.id == student.group_id
        ))
    )
    subject = subject_query.scalar_one_or_none()

    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Предмет не найден или нет доступа"
        )

    # Получаем материалы для группы студента
    materials = await db.execute(
        select(CourseMaterial)
        .where(and_(
            CourseMaterial.subject_id == subject_id,
            CourseMaterial.group_id == student.group_id
        ))
    )
    materials = materials.scalars().all()

    # Формируем ответ
    return {
        "subject": {
            "id": subject.id,
            "name": subject.name,
            "type": subject.type,
            "teacher": f"{subject.teacher.user.last_name} {subject.teacher.user.first_name}"
        },
        "materials": [
            {
                "id": m.id,
                "title": m.title,
                "type": m.type,
                "deadline": m.deadline,
                "description": m.description
            } for m in materials
        ],
        "group_info": {
            "group_id": student.group_id,
            "group_number": student.group.number
        }
    }