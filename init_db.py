from agent.nodes import get_conn

with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS gastos CASCADE;
            DROP TABLE IF EXISTS presupuestos CASCADE;

            CREATE TABLE gastos (
                id        SERIAL PRIMARY KEY,
                user_id   INTEGER NOT NULL,
                categoria VARCHAR(255) NOT NULL,
                monto     NUMERIC(12, 2) NOT NULL,
                fecha     DATE NOT NULL
            );

            CREATE TABLE presupuestos (
                user_id INTEGER NOT NULL,
                mes     VARCHAR(7) NOT NULL,
                monto   NUMERIC(12, 2) NOT NULL,
                PRIMARY KEY (user_id, mes)
            );

            CREATE INDEX idx_gastos_user_fecha
                ON gastos(user_id, fecha);
        """)

print("Base de datos inicializada correctamente.")