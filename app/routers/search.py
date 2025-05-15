from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, cast, or_, select, text
from sqlalchemy.orm import selectinload

from app.models import models
from app.dependencies import templates
from app.auth import get_current_user
from app import database

router = APIRouter(
    prefix="/search",
    tags=["search"]
)

@router.get("", response_class=HTMLResponse)
async def search_page(
    request: Request,
    current_user: models.User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "current_user": current_user}
    )

@router.get("/results")
async def search_results(
    query: str,
    db: AsyncSession = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    if len(query) < 3:
        return JSONResponse(content={"results": []})

    # Поиск по предметам (оставляем без изменений)
    subjects_result = await db.execute(
        select(models.Subject)
        .options(
            selectinload(models.Subject.teacher)
            .selectinload(models.Teacher.user)
        )
        .where(models.Subject.name.ilike(f"%{query}%"))
        .limit(5)
    )
    subjects = subjects_result.scalars().all()

    # Исправленный поиск по преподавателям
    teachers_query = select(models.User).join(
        models.Teacher, 
        models.User.id == models.Teacher.user_id
    ).where(
        cast(models.User.role, String) == "teacher",  # Явное приведение ENUM к строке
        or_(
            models.User.first_name.ilike(f"%{query}%"),
            models.User.last_name.ilike(f"%{query}%"),
            models.User.patronymic.ilike(f"%{query}%")
        )
    ).limit(5)

    teachers_result = await db.execute(teachers_query)
    teachers = teachers_result.scalars().all()

    # Формирование результатов (оставляем без изменений)
    results = {
        "subjects": [
            {
                "id": subj.id,
                "name": subj.name,
                "type": subj.type,
                "teacher": f"{subj.teacher.user.last_name} {subj.teacher.user.first_name}",
                "url": f"/subjects/{subj.id}"
            } for subj in subjects
        ],
        "teachers": [
            {
                "id": teacher.id,
                "name": f"{teacher.last_name} {teacher.first_name} {teacher.patronymic or ''}",
                "url": f"/teachers/{teacher.id}"
            } for teacher in teachers
        ]
    }

    return JSONResponse(content={"results": results})
