-- 001_create_users.sql
-- 用户表 — GitHub OAuth 认证用户
-- 执行方式：mysql -u root -p aioperator < migrations/001_create_users.sql

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(200) DEFAULT NULL UNIQUE,
    github_id INT NOT NULL UNIQUE,
    avatar_url VARCHAR(500) DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
