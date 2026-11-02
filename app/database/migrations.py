import sqlite3

MIGRATIONS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        short_name TEXT DEFAULT '',
        default_hours INTEGER NOT NULL DEFAULT 2,
        grade INTEGER,
        alan TEXT DEFAULT '',
        dal TEXT DEFAULT '',
        brans TEXT DEFAULT '',
        difficulty INTEGER NOT NULL DEFAULT 0,
        physical INTEGER NOT NULL DEFAULT 0,
        preferred_time TEXT NOT NULL DEFAULT 'any',
        room_type TEXT DEFAULT '',
        room_required INTEGER NOT NULL DEFAULT 0,
        min_block INTEGER NOT NULL DEFAULT 1,
        max_block INTEGER NOT NULL DEFAULT 2,
        allowed_splits TEXT DEFAULT '',
        forbidden_splits TEXT DEFAULT '',
        preferred_split TEXT DEFAULT '',
        allow_same_day INTEGER NOT NULL DEFAULT 0,
        elective INTEGER NOT NULL DEFAULT 0,
        vocational INTEGER NOT NULL DEFAULT 0,
        color TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS curricula (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        grade INTEGER,
        alan TEXT DEFAULT '',
        dal TEXT DEFAULT '',
        program_type TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS curriculum_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        curriculum_id INTEGER NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        hours INTEGER NOT NULL,
        UNIQUE (curriculum_id, subject_id)
    );

    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        brans TEXT DEFAULT '',
        max_daily INTEGER NOT NULL DEFAULT 8,
        max_weekly INTEGER NOT NULL DEFAULT 30,
        min_weekly INTEGER NOT NULL DEFAULT 0,
        max_consecutive INTEGER NOT NULL DEFAULT 6,
        preferred_days TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS teacher_subjects (
        teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        PRIMARY KEY (teacher_id, subject_id)
    );

    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        room_type TEXT NOT NULL DEFAULT 'Derslik',
        capacity INTEGER NOT NULL DEFAULT 0,
        equipment TEXT DEFAULT '',
        alan TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS room_subjects (
        room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        PRIMARY KEY (room_id, subject_id)
    );

    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        grade INTEGER NOT NULL DEFAULT 9,
        alan TEXT DEFAULT '',
        dal TEXT DEFAULT '',
        program_type TEXT DEFAULT 'Anadolu Meslek Programı',
        curriculum_id INTEGER REFERENCES curricula(id) ON DELETE SET NULL,
        home_room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
        student_count INTEGER NOT NULL DEFAULT 0,
        weekly_hours INTEGER NOT NULL DEFAULT 0,
        max_daily INTEGER NOT NULL DEFAULT 0,
        available_days TEXT NOT NULL DEFAULT '0,1,2,3,4',
        notes TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS class_extra_lessons (
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        hours INTEGER NOT NULL,
        PRIMARY KEY (class_id, subject_id)
    );

    CREATE TABLE IF NOT EXISTS class_fixed_teachers (
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
        PRIMARY KEY (class_id, subject_id)
    );

    CREATE TABLE IF NOT EXISTS unavailability (
        entity_type TEXT NOT NULL CHECK (entity_type IN ('teacher', 'room', 'class')),
        entity_id INTEGER NOT NULL,
        day INTEGER NOT NULL,
        period INTEGER NOT NULL,
        PRIMARY KEY (entity_type, entity_id, day, period)
    );

    CREATE TABLE IF NOT EXISTS timetables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'auto',
        status TEXT DEFAULT '',
        objective REAL,
        solve_seconds REAL,
        notes TEXT DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS timetable_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timetable_id INTEGER NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
        room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
        day INTEGER NOT NULL,
        period INTEGER NOT NULL,
        block INTEGER NOT NULL DEFAULT 0,
        locked INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_entries_tt ON timetable_entries(timetable_id);
    CREATE INDEX IF NOT EXISTS idx_unavail ON unavailability(entity_type, entity_id);
    """,
]


def migrate(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version in range(current, len(MIGRATIONS)):
        conn.executescript(MIGRATIONS[version])
        conn.execute(f"PRAGMA user_version = {version + 1}")
    conn.commit()
    return len(MIGRATIONS)
