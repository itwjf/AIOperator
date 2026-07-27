-- init_all.sql
-- AIOperator 数据库初始化 — 一次性执行所有迁移
-- 使用方式：mysql -u root -p aioperator < migrations/init_all.sql

SOURCE migrations/001_create_users.sql;
SOURCE migrations/002_create_sessions.sql;
SOURCE migrations/003_create_messages.sql;
SOURCE migrations/004_create_readonly_user.sql;
