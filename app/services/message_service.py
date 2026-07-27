"""
消息服务 — 消息存取，按会话隔离。
"""
from app.core.db import get_db_connection


def add_message(session_fk: int, role: str, content: str, tool_name: str = None) -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, tool_name) VALUES (%s,%s,%s,%s)",
                (session_fk, role, content, tool_name),
            )
        conn.commit()
        msg_id = cursor.lastrowid
    finally:
        conn.close()
    return msg_id


def get_messages(session_fk: int, limit: int = 100) -> list[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, role, content, tool_name, created_at FROM messages "
                "WHERE session_id=%s ORDER BY id DESC LIMIT %s",
                (session_fk, limit),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    # 反转回时间正序（因为 SQL 是 DESC + LIMIT）
    rows.reverse()
    return list(rows)


def delete_messages(session_fk: int) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM messages WHERE session_id=%s", (session_fk,))
        conn.commit()
    finally:
        conn.close()


def save_conversation(session_fk: int, messages: list[dict]) -> None:
    """批量保存对话消息。messages 中每条为 {role, content, tool_name}。"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for msg in messages:
                cursor.execute(
                    "INSERT INTO messages (session_id, role, content, tool_name) VALUES (%s,%s,%s,%s)",
                    (session_fk, msg["role"], msg["content"], msg.get("tool_name")),
                )
        conn.commit()
    finally:
        conn.close()
