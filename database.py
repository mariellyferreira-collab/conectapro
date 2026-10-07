import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import unicodedata


ROOT = Path(__file__).resolve().parent
DATABASE_DIRECTORY = ROOT / ".private"
DATABASE_PATH = DATABASE_DIRECTORY / "conecta_protecao.sqlite3"
SCHEMA_VERSION = 2
PASSWORD_HASH_ITERATIONS = 600_000
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 24
BLOCKED_USERNAME_WORDS = frozenset({
    "arrombado", "arrombada", "bosta", "buceta", "bucetao", "caralho",
    "caralhudo", "cuzao", "cuzona", "fdp", "foda", "fodase", "fodido",
    "fodida", "merda", "piranha", "porra", "puta", "putaria", "puto",
    "retardado", "retardada", "viado", "vadia", "vagabundo", "vagabunda",
})


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE accounts (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        username_normalized TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
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
    "usuario": ("account:read:self", "account:update:self"),
    "jovem": ("account:read:self", "account:update:self"),
    "responsavel": ("account:read:self", "account:update:self"),
    "profissional": ("account:read:self", "account:update:self"),
    "administrador": (
        "account:read:self",
        "account:update:self",
        "account:manage",
        "content:manage",
    ),
}


def normalize_username(username):
    return unicodedata.normalize("NFKC", username).strip().casefold()


def validate_username(username):
    if not isinstance(username, str):
        raise ValueError("Informe um nome de usuário válido.")

    normalized = normalize_username(username)
    if not USERNAME_MIN_LENGTH <= len(normalized) <= USERNAME_MAX_LENGTH:
        raise ValueError("O nome de usuário deve ter entre 3 e 24 caracteres.")
    if not (normalized[0].isalnum() and normalized[-1].isalnum()):
        raise ValueError("Use letras ou números no início e no fim do nome de usuário.")
    if any(not (character.isalpha() or character.isdigit() or character in "_.-") for character in normalized):
        raise ValueError("Use somente letras, números, ponto, hífen ou sublinhado no nome de usuário.")

    ascii_name = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z]+|\d+", ascii_name)
    if any(word in BLOCKED_USERNAME_WORDS for word in words):
        raise ValueError("Escolha um nome de usuário respeitoso, sem termos ofensivos.")

    return normalized


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return "pbkdf2_sha256$%d$%s$%s" % (
        PASSWORD_HASH_ITERATIONS,
        encoded_salt,
        encoded_digest,
    )


def verify_password(password, stored_hash):
    try:
        scheme, iterations_text, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = base64.urlsafe_b64decode(encoded_salt + "=" * (-len(encoded_salt) % 4))
        expected = base64.urlsafe_b64decode(encoded_digest + "=" * (-len(encoded_digest) % 4))
    except (AttributeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_account(username, password, role="usuario", database_path=DATABASE_PATH):
    normalized_username = validate_username(username)
    if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
        raise ValueError("A senha deve ter entre 12 e 256 caracteres.")
    if role not in ROLE_PERMISSIONS:
        raise ValueError("O perfil solicitado não é válido.")

    initialize_database(database_path)
    account_id = secrets.token_hex(16)
    password_hash = hash_password(password)

    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO accounts (id, username, username_normalized, password_hash) VALUES (?, ?, ?, ?)",
            (account_id, unicodedata.normalize("NFKC", username).strip(), normalized_username, password_hash),
        )

        connection.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role,))
        role_id = connection.execute(
            "SELECT id FROM roles WHERE name = ?", (role,)
        ).fetchone()["id"]
        for permission_code in ROLE_PERMISSIONS[role]:
            connection.execute(
                "INSERT OR IGNORE INTO permissions (code) VALUES (?)",
                (permission_code,),
            )
            permission_id = connection.execute(
                "SELECT id FROM permissions WHERE code = ?", (permission_code,)
            ).fetchone()["id"]
            connection.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                (role_id, permission_id),
            )

        connection.execute(
            "INSERT INTO account_roles (account_id, role_id) VALUES (?, ?)",
            (account_id, role_id),
        )
        connection.commit()
        return account_id
    except sqlite3.IntegrityError as error:
        if connection.in_transaction:
            connection.rollback()
        if "username_normalized" in str(error):
            raise ValueError("Esse nome de usuário já está em uso.") from error
        raise
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def authenticate_account(username, password, database_path=DATABASE_PATH):
    try:
        normalized_username = validate_username(username)
    except ValueError:
        return None
    connection = connect_database(database_path)
    try:
        account = connection.execute(
            "SELECT id, username, password_hash FROM accounts WHERE username_normalized = ? AND is_active = 1",
            (normalized_username,),
        ).fetchone()
        if account is None or not verify_password(password, account["password_hash"]):
            return None
        return {"id": account["id"], "username": account["username"]}
    finally:
        connection.close()


def create_session(account_id, token_hash, expires_at, database_path=DATABASE_PATH):
    connection = connect_database(database_path)
    try:
        connection.execute(
            "INSERT INTO sessions (id, account_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
            (secrets.token_hex(16), account_id, token_hash, expires_at),
        )
        connection.commit()
    finally:
        connection.close()


def account_for_session(token_hash, now, database_path=DATABASE_PATH):
    connection = connect_database(database_path)
    try:
        account = connection.execute(
            """
            SELECT accounts.id, accounts.username
            FROM sessions
            JOIN accounts ON accounts.id = sessions.account_id
            WHERE sessions.token_hash = ?
                AND sessions.revoked_at IS NULL
                AND sessions.expires_at > ?
                AND accounts.is_active = 1
            """,
            (token_hash, now),
        ).fetchone()
        return dict(account) if account else None
    finally:
        connection.close()


def revoke_session(token_hash, revoked_at, database_path=DATABASE_PATH):
    connection = connect_database(database_path)
    try:
        connection.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (revoked_at, token_hash),
        )
        connection.commit()
    finally:
        connection.close()


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

        if schema_version == 1:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ALTER TABLE accounts RENAME COLUMN email TO username")
            connection.execute("ALTER TABLE accounts RENAME COLUMN email_normalized TO username_normalized")
            connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            connection.commit()
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
