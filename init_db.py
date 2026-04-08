import psycopg2, os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    categoria VARCHAR(100),
    monto DECIMAL(12,2),
    fecha DATE
);

CREATE TABLE IF NOT EXISTS presupuestos (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    mes VARCHAR(7),
    monto DECIMAL(12,2),
    UNIQUE(user_id, mes)
);

CREATE TABLE IF NOT EXISTS vacas (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    nombre VARCHAR(100),
    num_personas INT DEFAULT 1,
    cerrada BOOLEAN DEFAULT FALSE,
    fecha_creacion DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS vaca_gastos (
    id SERIAL PRIMARY KEY,
    vaca_id INT REFERENCES vacas(id) ON DELETE CASCADE,
    descripcion VARCHAR(100),
    monto DECIMAL(12,2),
    fecha DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS deudas (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tipo VARCHAR(10),
    persona VARCHAR(100),
    monto DECIMAL(12,2),
    descripcion TEXT,
    fecha DATE DEFAULT CURRENT_DATE,
    pagado BOOLEAN DEFAULT FALSE
);
""")

conn.commit()
cur.close()
conn.close()
print("✅ Tablas creadas correctamente")