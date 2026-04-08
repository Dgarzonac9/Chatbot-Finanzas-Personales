import psycopg2, json, os
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from datetime import date
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
MODELO_LLM   = os.getenv("MODELO_LLM")
API_KEY      = os.getenv("GROQ_API_KEY")

client = Groq(api_key=API_KEY)

# ── Connection pool ────────────────────────────────────────────────────────

_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL,
    cursor_factory=psycopg2.extras.DictCursor,
)

@contextmanager
def get_conn():
    """Context manager que devuelve una conexión del pool y la libera al salir."""
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()          # commit explícito en operaciones de escritura
    except Exception:
        conn.rollback()        # rollback si algo falla
        raise
    finally:
        _pool.putconn(conn)    # siempre devuelve la conexión al pool


# ── Utilidades ─────────────────────────────────────────────────────────────

def _validar_user_id(state: dict) -> int:
    """Valida y retorna el user_id. Lanza ValueError si no es válido."""
    user_id = state.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"user_id inválido: {user_id!r}")
    return user_id


def extraer_gasto_llm(texto: str):
    """Extrae categoría, monto y fecha de un texto usando el LLM."""
    prompt = f"""
    Extrae del texto el gasto en JSON:
    {{"categoría": "...", "monto": ..., "fecha": "YYYY-MM-DD"}}
    Si no hay fecha explícita usa hoy: {date.today()}.
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        # response_format json_object garantiza JSON válido, no se necesita doble parse
        data = json.loads(resp.choices[0].message.content)
        if not data.get("fecha"):
            data["fecha"] = str(date.today())
        return (
            data.get("categoría", "desconocido"),
            float(data.get("monto", 0)),
            data["fecha"],
        )
    except Exception as e:
        print("Error extrayendo gasto:", e)
        return "desconocido", 0.0, str(date.today())


def formatear_respuesta(datos_crudos: str) -> str:
    """Convierte datos en una respuesta natural con el LLM."""
    prompt = f"""
    Eres un asistente de finanzas personales amigable.
    Convierte estos datos en un mensaje claro y amigable en español.
    Datos: {datos_crudos}
    Responde de forma breve y directa, puedes usar emojis.
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


# ── Nodo 1: Guardar gasto ──────────────────────────────────────────────────

def guardar_gasto(state: dict) -> dict:
    user_id = _validar_user_id(state)
    categoria, monto, fecha = extraer_gasto_llm(state["input"])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gastos (user_id, categoria, monto, fecha) VALUES (%s, %s, %s, %s)",
                (user_id, categoria, monto, fecha),
            )

    respuesta = formatear_respuesta(
        f"Gasto guardado: {monto} COP en '{categoria}' el {fecha}"
    )
    return {"output": respuesta}


# ── Nodo 2: Reporte del día ────────────────────────────────────────────────

def reporte_dia(state: dict) -> dict:
    user_id = _validar_user_id(state)
    hoy = str(date.today())

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT categoria, SUM(monto) AS total
                FROM gastos
                WHERE user_id = %s AND fecha = %s
                GROUP BY categoria
                ORDER BY total DESC
                """,
                (user_id, hoy),
            )
            filas = cur.fetchall()

            cur.execute(
                "SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE user_id = %s AND fecha = %s",
                (user_id, hoy),
            )
            total = cur.fetchone()[0]

    if not filas:
        return {"output": "No registré gastos tuyos hoy 🎉"}

    desglose = ", ".join([f"{cat}: ${round(m):,}" for cat, m in filas])
    respuesta = formatear_respuesta(
        f"Reporte del {hoy}. Total: ${round(total):,}. Desglose: {desglose}"
    )
    return {"output": respuesta}


# ── Nodo 3: Reporte del mes ────────────────────────────────────────────────

def reporte_mes(state: dict) -> dict:
    user_id = _validar_user_id(state)
    hoy = date.today()
    mes  = hoy.strftime("%Y-%m")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT categoria, SUM(monto) AS total
                FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                GROUP BY categoria
                ORDER BY total DESC
                """,
                (user_id, mes),
            )
            filas = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(SUM(monto), 0) FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                """,
                (user_id, mes),
            )
            total = cur.fetchone()[0]

            cur.execute(
                """
                SELECT fecha, SUM(monto) AS t FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                GROUP BY fecha ORDER BY t DESC LIMIT 1
                """,
                (user_id, mes),
            )
            dia_top = cur.fetchone()

    if not filas:
        return {"output": f"Sin gastos registrados en {mes} 🎉"}

    desglose = ", ".join([f"{cat}: ${round(m):,}" for cat, m in filas])
    extra = (
        f"Día con más gasto: {dia_top[0]} (${round(dia_top[1]):,})" if dia_top else ""
    )
    respuesta = formatear_respuesta(
        f"Reporte {mes}. Total: ${round(total):,}. {extra}. Por categoría: {desglose}"
    )
    return {"output": respuesta}


# ── Nodo 4: Reporte por categoría ─────────────────────────────────────────

def reporte_categoria(state: dict) -> dict:
    user_id = _validar_user_id(state)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT categoria, SUM(monto) AS total, COUNT(*) AS veces
                FROM gastos
                WHERE user_id = %s
                GROUP BY categoria
                ORDER BY total DESC
                """,
                (user_id,),
            )
            filas = cur.fetchall()

    if not filas:
        return {"output": "Aún no tienes gastos registrados 📊"}

    resumen = "; ".join([f"{cat}: ${round(t):,} ({v} veces)" for cat, t, v in filas])
    respuesta = formatear_respuesta(f"Historial de gastos por categoría: {resumen}")
    return {"output": respuesta}


# ── Nodo 5: Editar / eliminar gasto ───────────────────────────────────────

def editar_gasto(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto   = state["input"]

    prompt = f"""
    El usuario quiere eliminar un gasto. Extrae en JSON:
    {{"accion": "ultimo" | "por_categoria" | "por_fecha",
      "categoria": "..." (opcional),
      "fecha": "YYYY-MM-DD" (opcional)}}
    Texto: "{texto}"
    Fecha de hoy: {date.today()}
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
    except Exception:
        params = {"accion": "ultimo"}

    accion = params.get("accion", "ultimo")

    with get_conn() as conn:
        with conn.cursor() as cur:
            if accion == "ultimo":
                cur.execute(
                    "SELECT id FROM gastos WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute("DELETE FROM gastos WHERE id = %s", (row["id"],))
                    return {"output": "✅ Eliminé tu último gasto registrado."}

            elif accion == "por_categoria" and params.get("categoria"):
                fecha = params.get("fecha", str(date.today()))
                cur.execute(
                    "DELETE FROM gastos WHERE user_id = %s AND categoria = %s AND fecha = %s",
                    (user_id, params["categoria"], fecha),
                )
                if cur.rowcount:
                    return {"output": f"✅ Eliminé los gastos de '{params['categoria']}' del {fecha}."}

            elif accion == "por_fecha" and params.get("fecha"):
                cur.execute(
                    "DELETE FROM gastos WHERE user_id = %s AND fecha = %s",
                    (user_id, params["fecha"]),
                )
                if cur.rowcount:
                    return {"output": f"✅ Eliminé los gastos del día {params['fecha']}."}

    return {"output": "No encontré el gasto que mencionas. ¿Puedes ser más específico?"}


# ── Nodo 6: Presupuesto y alertas ─────────────────────────────────────────

def presupuesto(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto   = state["input"]
    mes     = date.today().strftime("%Y-%m")

    prompt = f"""
    El usuario quiere establecer o consultar un presupuesto mensual.
    Extrae en JSON: {{"accion": "establecer" | "consultar", "monto": ... (solo si establece)}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
    except Exception:
        params = {"accion": "consultar"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            if params.get("accion") == "establecer" and params.get("monto"):
                cur.execute(
                    """
                    INSERT INTO presupuestos (user_id, mes, monto)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, mes) DO UPDATE SET monto = EXCLUDED.monto
                    """,
                    (user_id, mes, float(params["monto"])),
                )
                presupuesto_val = float(params["monto"])
            else:
                cur.execute(
                    "SELECT monto FROM presupuestos WHERE user_id = %s AND mes = %s",
                    (user_id, mes),
                )
                row = cur.fetchone()
                if not row:
                    return {
                        "output": f"No tienes presupuesto definido para {mes}. "
                                  "Dime cuánto quieres gastar este mes y lo guardo 💰"
                    }
                presupuesto_val = float(row["monto"])

            cur.execute(
                """
                SELECT COALESCE(SUM(monto), 0) FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                """,
                (user_id, mes),
            )
            gastado = float(cur.fetchone()[0])

    porcentaje = (gastado / presupuesto_val * 100) if presupuesto_val else 0
    restante   = presupuesto_val - gastado
    alerta = (
        "⚠️ ¡Superaste el presupuesto!"       if gastado > presupuesto_val else
        "🟡 Vas por más del 80%, con cuidado." if porcentaje > 80          else
        "✅ Vas bien."
    )

    respuesta = formatear_respuesta(
        f"Presupuesto {mes}: ${round(presupuesto_val):,}. "
        f"Gastado: ${round(gastado):,} ({round(porcentaje)}%). "
        f"Restante: ${round(restante):,}. {alerta}"
    )
    return {"output": respuesta}