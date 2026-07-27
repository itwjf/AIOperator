-- 002_create_sessions.sql
-- 会话表 — 按 user_id 隔离用户会话
-- 执行方式：mysql -u root -p aioperator < migrations/002_create_sessions.sql

CREATE TABLE IF NOT EXISTS sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    user_id INT NOT NULL,
    title VARCHAR(100) DEFAULT NULL,
    agent_type ENUM('rag', 'manual', 'mcp', 'aiops') NOT NULL DEFAULT 'rag',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_session (user_id, session_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
