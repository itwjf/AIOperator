-- 003_create_messages.sql
-- 消息表 — 按会话存取对话历史，替代 localStorage
-- 执行方式：mysql -u root -p aioperator < migrations/003_create_messages.sql

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    role ENUM('user', 'assistant', 'tool', 'system') NOT NULL,
    content TEXT NOT NULL,
    tool_name VARCHAR(100) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
