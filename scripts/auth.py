"""Autenticacao local para o painel Nexo Glosas."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PBKDF2_ITERATIONS = 240_000
SESSION_SECONDS = 12 * 60 * 60
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,40}$")


class AuthError(ValueError):
    """Entrada de autenticacao invalida."""


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'analyst')),
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checklist_state (
                    item_id TEXT PRIMARY KEY,
                    checked INTEGER NOT NULL,
                    checked_by INTEGER REFERENCES users(id),
                    checked_at INTEGER NOT NULL
                );
                """
            )
            connection.commit()

    @staticmethod
    def _normalize_username(username: object) -> str:
        value = str(username or "").strip().lower()
        if not USERNAME_PATTERN.fullmatch(value):
            raise AuthError("Usuario deve ter 3 a 40 caracteres: letras minusculas, numeros, ponto, hifen ou sublinhado.")
        return value

    @staticmethod
    def _validate_password(password: object) -> str:
        value = str(password or "")
        if len(value) < 10:
            raise AuthError("A senha deve ter pelo menos 10 caracteres.")
        if len(value) > 200:
            raise AuthError("A senha excede o limite permitido.")
        return value

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)

    def configured(self) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_user(self, username: object, display_name: object, password: object, role: str) -> dict:
        normalized = self._normalize_username(username)
        name = str(display_name or "").strip()
        if not 3 <= len(name) <= 80:
            raise AuthError("Nome deve ter entre 3 e 80 caracteres.")
        if role not in {"admin", "analyst"}:
            raise AuthError("Perfil invalido.")
        valid_password = self._validate_password(password)
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(valid_password, salt)
        now = int(time.time())
        try:
            with closing(self._connect()) as connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, display_name, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (normalized, name, password_hash, salt, role, now),
                )
                connection.commit()
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise AuthError("Este usuario ja existe.") from exc
        return {"id": user_id, "username": normalized, "display_name": name, "role": role, "active": True}

    def create_initial_admin(self, username: object, display_name: object, password: object) -> dict:
        """Cria o primeiro acesso de forma atomica, evitando dois administradores iniciais."""
        normalized = self._normalize_username(username)
        name = str(display_name or "").strip()
        if not 3 <= len(name) <= 80:
            raise AuthError("Nome deve ter entre 3 e 80 caracteres.")
        valid_password = self._validate_password(password)
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(valid_password, salt)
        now = int(time.time())
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise AuthError("O acesso inicial ja foi configurado.")
                cursor = connection.execute(
                    "INSERT INTO users (username, display_name, password_hash, salt, role, created_at) "
                    "VALUES (?, ?, ?, ?, 'admin', ?)",
                    (normalized, name, password_hash, salt, now),
                )
                connection.commit()
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise AuthError("Este usuario ja existe.") from exc
        return {"id": user_id, "username": normalized, "display_name": name, "role": "admin", "active": True}

    def authenticate(self, username: object, password: object) -> dict | None:
        try:
            normalized = self._normalize_username(username)
        except AuthError:
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT id, username, display_name, password_hash, salt, role, active FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
        if not row or not row["active"]:
            return None
        candidate = self._password_hash(str(password or ""), row["salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        return self._public_user(row)

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "active": bool(row["active"]),
        }

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        now = int(time.time())
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (token_hash, user_id, now + SESSION_SECONDS, now),
            )
            connection.commit()
        return token

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
        now = int(time.time())
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.display_name, u.role, u.active
                  FROM sessions s JOIN users u ON u.id = s.user_id
                 WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
                """,
                (token_hash, now),
            ).fetchone()
        return self._public_user(row) if row else None

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            connection.commit()

    def list_users(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, username, display_name, role, active FROM users ORDER BY display_name, username"
            ).fetchall()
        return [self._public_user(row) for row in rows]

    def checklist_state(self) -> dict[str, dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT c.item_id, c.checked, c.checked_at, u.display_name
                  FROM checklist_state c LEFT JOIN users u ON u.id = c.checked_by
                """
            ).fetchall()
        return {
            row["item_id"]: {
                "checked": bool(row["checked"]),
                "checked_at": row["checked_at"],
                "checked_by": row["display_name"],
            }
            for row in rows
        }

    def set_checklist(self, item_id: str, checked: bool, user_id: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO checklist_state (item_id, checked, checked_by, checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    checked = excluded.checked,
                    checked_by = excluded.checked_by,
                    checked_at = excluded.checked_at
                """,
                (item_id, int(checked), user_id, int(time.time())),
            )
            connection.commit()
