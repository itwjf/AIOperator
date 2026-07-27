"""
数据库工具 — 提供 MySQL 连接获取函数。
"""
import pymysql
from app.config import settings


def get_db_connection():
    """创建 MySQL 连接（调用方负责 conn.close()）。"""
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
