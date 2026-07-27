"""
会话服务 — 会话 CRUD，按 user_id 隔离。
"""
import pymysql
from app.core.db import get_db_connection


def create_session(user_id: int, session_id: str, agent_type: str = "rag", title: str = None) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sessions (session_id, user_id, agent_type, title) VALUES (%s,%s,%s,%s)",
                (session_id, user_id, agent_type, title),
            )
        conn.commit()
    except pymysql.IntegrityError:
        return {"session_id": session_id, "agent_type": agent_type, "title": title, "exists": True}
    finally:
        conn.close()
    return {"session_id": session_id, "agent_type": agent_type, "title": title}


def list_sessions(user_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT session_id, title, agent_type, created_at, updated_at "
                "FROM sessions WHERE user_id=%s ORDER BY updated_at DESC",
                (user_id,),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    return list(rows)


def get_session_internal_id(user_id: int, session_id: str) -> int | None:
    """通过 UUID session_id 获取内部自增 ID（供 message_service 使用）。"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM sessions WHERE user_id=%s AND session_id=%s",
                (user_id, session_id),
            )
            row = cursor.fetchone()
    finally:
        conn.close()
    return row["id"] if row else None


def delete_session(user_id: int, session_id: str) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM sessions WHERE user_id=%s AND session_id=%s",
                (user_id, session_id),
            )
        conn.commit()
        affected = cursor.rowcount
    finally:
        conn.close()
    return affected > 0


def update_session_title(user_id: int, session_id: str, title: str) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sessions SET title=%s WHERE user_id=%s AND session_id=%s",
                (title, user_id, session_id),
            )
        conn.commit()
        affected = cursor.rowcount
    finally:
        conn.close()
    return affected > 0
