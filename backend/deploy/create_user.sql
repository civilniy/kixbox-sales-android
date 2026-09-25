-- Выполнить на сервере Б: clickhouse-client --multiquery < deploy/create_user.sql
-- Пароль заменить на тот же, что в .env (CLICKHOUSE_PASSWORD).
CREATE USER IF NOT EXISTS sales_app
    IDENTIFIED WITH sha256_password BY 'придумайте-длинный-пароль'
    HOST LOCAL
    SETTINGS readonly = 1, max_execution_time = 90, max_memory_usage = 1500000000;

GRANT SELECT ON kixbox.* TO sales_app;
GRANT SELECT ON brandshop.* TO sales_app;
GRANT SELECT ON nuwstore.* TO sales_app;
GRANT SELECT ON studioslow.* TO sales_app;
GRANT SELECT ON leform.* TO sales_app;
