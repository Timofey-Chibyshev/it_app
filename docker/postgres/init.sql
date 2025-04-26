-- Создание таблиц с проверкой на существование
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    number VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    patronymic VARCHAR(50),
    email VARCHAR(100) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(10) CHECK (role IN ('student', 'teacher')) NOT NULL,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS students (
    user_id INTEGER PRIMARY KEY,
    group_id INTEGER,
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS teachers (
    user_id INTEGER PRIMARY KEY,
    position VARCHAR(100) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Добавлено UNIQUE для name
CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(10) CHECK (type IN ('lecture', 'practice')) NOT NULL,
    teacher_id INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES teachers(user_id)
);

CREATE TABLE IF NOT EXISTS course_materials (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(10) CHECK (type IN ('lecture', 'practice', 'assignment')) NOT NULL,
    created_at TIMESTAMP,
    deadline TIMESTAMP CHECK (deadline > CURRENT_TIMESTAMP),
    subject_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

CREATE TABLE IF NOT EXISTS group_subject (
    group_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    PRIMARY KEY (group_id, subject_id),
    FOREIGN KEY (group_id) REFERENCES groups(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id SERIAL PRIMARY KEY,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL CHECK (end_time > start_time),
    subject_id INTEGER NOT NULL,
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

CREATE TABLE IF NOT EXISTS assignment_submissions (
    id SERIAL PRIMARY KEY,
    submission_date TIMESTAMP,
    status VARCHAR(10) CHECK (status IN ('submitted', 'graded', 'rejected')),
    grade INTEGER CHECK (grade BETWEEN 0 AND 100),
    feedback TEXT,
    file_path VARCHAR(255),
    student_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,
    FOREIGN KEY (material_id) REFERENCES course_materials(id),
    FOREIGN KEY (student_id) REFERENCES students(user_id)
);

-- Вставка данных с проверкой на дубликаты
INSERT INTO users (first_name, last_name, email, hashed_password, role, is_active)
VALUES 
('Препод', 'Преподов', 'teacher@edu.ru', 'hashed_teacher_password', 'teacher', TRUE)
ON CONFLICT (email) DO NOTHING;

INSERT INTO users (first_name, last_name, email, hashed_password, role, is_active)
VALUES 
('Студент', 'Студентов', 'student@edu.ru', 'hashed_student_password', 'student', TRUE)
ON CONFLICT (email) DO NOTHING;

INSERT INTO groups (number)
VALUES ('ГРУЗ-200')
ON CONFLICT (number) DO NOTHING;

INSERT INTO teachers (user_id, position)
VALUES (1, 'Профессор')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO students (user_id, group_id)
VALUES (2, 1)
ON CONFLICT (user_id) DO NOTHING;

-- Исправлено: ON CONFLICT (name) работает благодаря UNIQUE
INSERT INTO subjects (name, type, teacher_id)
VALUES ('Работа с данными', 'practice', 1)
ON CONFLICT (name) DO NOTHING;

INSERT INTO group_subject (group_id, subject_id)
VALUES (1, 1)
ON CONFLICT (group_id, subject_id) DO NOTHING;

-- Убраны ON CONFLICT (нет уникального индекса на title+subject_id)
INSERT INTO course_materials (title, file_path, type, deadline, subject_id, group_id)
VALUES 
('Введение в SQL', '/materials/sql_intro.pdf', 'lecture', '2025-12-12 12:00:00', 1, 1);