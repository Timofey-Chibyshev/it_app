import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import text
from app.models import models
from app.auth import get_password_hash

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@postgres/edu_platform_db"
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS users, groups, subjects, course_materials, assignment_submissions, schedules, teachers, students, group_subject CASCADE"))
        await conn.run_sync(models.Base.metadata.create_all)

    async with async_session() as session:
        try:
            # Создаем преподавателей
            teachers_data = [
                {
                    "first_name": "Иван",
                    "last_name": "Преподавателев",
                    "patronymic": "Петрович",
                    "email": "teacher1@edu.ru",
                    "password": "teacher123",
                    "position": "Профессор"
                },
                {
                    "first_name": "Мария",
                    "last_name": "Ученова",
                    "patronymic": "Сергеевна",
                    "email": "teacher2@edu.ru",
                    "password": "teacher456",
                    "position": "Доцент"
                }
            ]
            
            teachers = []
            for data in teachers_data:
                user = models.User(
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    patronymic=data["patronymic"],
                    email=data["email"],
                    hashed_password=get_password_hash(data["password"]),
                    role="teacher",
                    is_active=True
                )
                session.add(user)
                await session.flush()
                
                teacher = models.Teacher(
                    user_id=user.id,
                    position=data["position"]
                )
                session.add(teacher)
                teachers.append(teacher)
            
            await session.flush()

            # Создаем группы
            groups_data = ["ИТ-21", "ИТ-22", "ИТ-23"]
            groups = []
            for number in groups_data:
                group = models.Group(number=number)
                session.add(group)
                groups.append(group)
            
            await session.flush()

            # Создаем студентов (3 в каждой группе)
            students = []
            for group in groups:
                for i in range(1, 4):
                    user = models.User(
                        first_name=f"Студент{i}",
                        last_name=group.number,
                        patronymic="Тестович",
                        email=f"student{group.id}_{i}@edu.ru",
                        hashed_password=get_password_hash("student123"),
                        role="student",
                        is_active=True
                    )
                    session.add(user)
                    await session.flush()
                    
                    student = models.Student(
                        user_id=user.id,
                        group_id=group.id
                    )
                    session.add(student)
                    students.append(student)
            
            await session.flush()

            # Создаем предметы
            subjects_data = [
                {"name": "Базы данных", "type": "practice", "teacher": teachers[0]},
                {"name": "Программирование", "type": "lecture", "teacher": teachers[0]},
                {"name": "Веб-разработка", "type": "practice", "teacher": teachers[1]},
                {"name": "Алгоритмы", "type": "lecture", "teacher": teachers[1]}
            ]
            
            subjects = []
            for data in subjects_data:
                subject = models.Subject(
                    name=data["name"],
                    type=data["type"],
                    teacher_id=data["teacher"].user_id
                )
                session.add(subject)
                subjects.append(subject)
            
            await session.flush()

            # Связываем группы и предметы
            group_subject_links = [
                (groups[0], subjects[0]), (groups[0], subjects[1]),
                (groups[1], subjects[1]), (groups[1], subjects[2]),
                (groups[2], subjects[2]), (groups[2], subjects[3])
            ]
            
            for group, subject in group_subject_links:
                await session.execute(
                    insert(models.group_subject).values(
                        group_id=group.id,
                        subject_id=subject.id
                    )
                )

            # Создаем учебные материалы
            materials_data = [
                # Для Базы данных
                {"title": "Введение в SQL", "type": "lecture", "subject": subjects[0], "group": groups[0]},
                {"title": "Нормализация", "type": "assignment", "subject": subjects[0], "group": groups[0], "deadline": datetime.now() + timedelta(days=30)},
                
                # Для Программирования
                {"title": "Основы Python", "type": "lecture", "subject": subjects[1], "group": groups[0]},
                {"title": "ООП", "type": "assignment", "subject": subjects[1], "group": groups[0], "deadline": datetime.now() + timedelta(days=20)},
                
                # Для Веб-разработки
                {"title": "HTML/CSS", "type": "practice", "subject": subjects[2], "group": groups[1]},
                {"title": "JavaScript", "type": "assignment", "subject": subjects[2], "group": groups[1], "deadline": datetime.now() + timedelta(days=25)},
                
                # Для Алгоритмов
                {"title": "Сортировки", "type": "lecture", "subject": subjects[3], "group": groups[2]},
                {"title": "Динамическое программирование", "type": "assignment", "subject": subjects[3], "group": groups[2], "deadline": datetime.now() + timedelta(days=35)}
            ]
            
            materials = []
            for data in materials_data:
                material = models.CourseMaterial(
                    title=data["title"],
                    file_path=f"/materials/{data['title'].replace(' ', '_')}.pdf",
                    description=f"Материал по теме: {data['title']}",
                    type=data["type"],
                    deadline=data.get("deadline"),
                    subject_id=data["subject"].id,
                    group_id=data["group"].id
                )
                session.add(material)
                materials.append(material)
            
            await session.flush()

            # Добавляем сданные задания
            submissions_data = []
            for material in materials:
                if material.type == "assignment":
                    # Выбираем студентов из группы материала
                    group_students = [s for s in students if s.group_id == material.group_id]
                    
                    for i, student in enumerate(group_students):
                        # 50% студентов сдали задание
                        if i % 2 == 0:
                            submissions_data.append({
                                "student": student,
                                "material": material,
                                "grade": 80 + i*5 if i < 3 else 90 - i*3,
                                "status": "graded" if i % 3 == 0 else "submitted"
                            })

            for data in submissions_data:
                submission = models.AssignmentSubmission(
                    student_id=data["student"].id,
                    material_id=data["material"].id,
                    file_path=f"/submissions/{data['student'].id}_{data['material'].id}.pdf",
                    grade=data["grade"],
                    feedback="Хорошая работа!" if data["grade"] > 85 else "Нужно доработать",
                    status=data["status"]
                )
                session.add(submission)

            # Добавляем расписание
            schedules = []
            for subject in subjects:
                for week in range(1, 4):
                    schedule = models.Schedule(
                        start_time=datetime.now() + timedelta(weeks=week, days=2),
                        end_time=datetime.now() + timedelta(weeks=week, days=2, hours=2),
                        subject_id=subject.id
                    )
                    schedules.append(schedule)
            
            session.add_all(schedules)

            await session.commit()
            print("✅ Тестовые данные успешно созданы!")

        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при инициализации БД: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(init_db())
    