-- 004_create_readonly_user.sql
-- 创建只读 MySQL 账号 — 用于 DB MCP Server，屏蔽敏感系统表
-- 执行方式：mysql -u root -p < migrations/004_create_readonly_user.sql
-- 注意：执行前请将 <生成随机密码> 替换为实际密码

CREATE USER IF NOT EXISTS 'aioperator_readonly'@'%' IDENTIFIED BY '<生成随机密码>';
-- 给业务表授权（按实际表名添加）
-- GRANT SELECT ON aioperator.your_business_table TO 'aioperator_readonly'@'%';
FLUSH PRIVILEGES;
