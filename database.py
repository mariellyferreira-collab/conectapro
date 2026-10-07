import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE_DIRECTORY = ROOT / ".private"
DATABASE_PATH = DATABASE_DIRECTORY / "conecta_protecao.sqlite3"
SCHEMA_VERSION = 1


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        email_normalized TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email_verified_at TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
    """
    CREATE TABLE roles (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE permissions (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE account_roles (
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
        granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        PRIMARY KEY (account_id, role_id)
    )
    """,
    """
    CREATE TABLE role_permissions (
        role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
        permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
        PRIMARY KEY (role_id, permission_id)
    )
    """,
    """
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        expires_at TEXT NOT NULL,
        revoked_at TEXT
    )
    """,
    "CREATE INDEX sessions_account_id_idx ON sessions(account_id)",
    "CREATE INDEX sessions_expires_at_idx ON sessions(expires_at)",
)

ROLE_PERMISSIONS = {
    "responsavel": ("account:read:self", "account:update:self"),
    "profissional": ("account:read:self", "account:update:self"),
    "administrador": (
        "account:read:self",
        "account:update:self",
        "account:manage",
        "content:manage",
    ),
}


def connect_database(database_path=DATABASE_PATH):
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize_database(database_path=DATABASE_PATH):
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect_database(database_path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if schema_version > SCHEMA_VERSION:
            raise RuntimeError(
                "O banco de dados foi criado por uma versão mais recente do Conecta Proteção."
            )
        if schema_version == SCHEMA_VERSION:
            return database_path

        connection.execute("BEGIN IMMEDIATE")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        for role_name, permission_codes in ROLE_PERMISSIONS.items():
            connection.execute(
                "INSERT INTO roles (name) VALUES (?)",
                (role_name,),
            )
            for permission_code in permission_codes:
                connection.execute(
                    "INSERT OR IGNORE INTO permissions (code) VALUES (?)",
                    (permission_code,),
                )
                permission_id = connection.execute(
                    "SELECT id FROM permissions WHERE code = ?",
                    (permission_code,),
                ).fetchone()["id"]
                role_id = connection.execute(
                    "SELECT id FROM roles WHERE name = ?",
                    (role_name,),
                ).fetchone()["id"]
                connection.execute(
                    "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                    (role_id, permission_id),
                )

        connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        connection.commit()
        return database_path
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
