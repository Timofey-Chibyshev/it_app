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
    id SERIAL PRIMARY KEY, -- Добавлен автоинкрементный ID
    user_id INTEGER UNIQUE NOT NULL, -- Уникальный внешний ключ
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
    FOREIGN KEY (student_id) REFERENCES students(id)
);
