import io
import psycopg2, json, os
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from datetime import date
from dotenv import load_dotenv
from groq import Groq
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

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

def _buscar_vaca(cur, user_id: int, nombre_vaca: str):
    """
    Busca una vaca por nombre de forma flexible.
    Primero intenta LIKE, si no encuentra intenta palabra por palabra.
    """
    # Intento 1: búsqueda normal
    cur.execute(
        "SELECT id, nombre, num_personas FROM vacas WHERE user_id = %s AND LOWER(nombre) LIKE LOWER(%s) ORDER BY id DESC LIMIT 1",
        (user_id, f"%{nombre_vaca}%"),
    )
    row = cur.fetchone()
    if row:
        return row

    # Intento 2: buscar por palabras individuales (ignora artículos cortos)
    palabras = [p for p in nombre_vaca.split() if len(p) > 3]
    for palabra in palabras:
        cur.execute(
            "SELECT id, nombre, num_personas FROM vacas WHERE user_id = %s AND LOWER(nombre) LIKE LOWER(%s) ORDER BY id DESC LIMIT 1",
            (user_id, f"%{palabra}%"),
        )
        row = cur.fetchone()
        if row:
            return row

    # Intento 3: mostrar todas las vacas del usuario para que elija
    return None

def _listar_vacas(cur, user_id: int) -> str:
    """Devuelve string con todas las vacas activas del usuario."""
    cur.execute(
        "SELECT id, nombre FROM vacas WHERE user_id = %s AND cerrada = FALSE ORDER BY id DESC",
        (user_id,),
    )
    vacas = cur.fetchall()
    if not vacas:
        return None
    return "\n".join([f"  {i+1}️⃣ *{v[1]}* (ID: {v[0]})" for i, v in enumerate(vacas)])

# ── Utilidades ─────────────────────────────────────────────────────────────

def _validar_user_id(state: dict) -> int:
    """Valida y retorna el user_id. Lanza ValueError si no es válido."""
    user_id = state.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"user_id inválido: {user_id!r}")
    return user_id

def extraer_gasto_llm(texto: str):
    prompt = f"""
    El usuario puede escribir con errores ortográficos o de forma informal.
    Interpreta el mensaje de forma flexible.

    El usuario quiere registrar un gasto personal.
    Extrae en JSON:
    {{
      "categoria": "...",
      "monto": ...,
      "fecha": "YYYY-MM-DD"
    }}
    Categorías posibles: comida, transporte, entretenimiento, salud, ropa, servicios, otro.
    Si no menciona fecha usa hoy: {date.today()}
    Si escribe "10k" interpreta como 10000, "20k" como 20000, etc.
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{{"role": "user", "content": prompt}}],
        response_format={{"type": "json_object"}},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        return (
            data.get("categoria", "otro"),
            float(data.get("monto", 0)),
            data.get("fecha", str(date.today())),
        )
    except Exception as e:
        print("Error extrayendo gasto:", e)
        return "otro", 0.0, str(date.today())

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

# ── Nodo 7: Crear vaca ─────────────────────────────────────────────────────

def crear_vaca(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere crear una vaca o fondo grupal.
    Extrae en JSON: {{"nombre": "..."}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        nombre = params.get("nombre", "Sin nombre")
    except Exception:
        nombre = "Sin nombre"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vacas (user_id, nombre) VALUES (%s, %s) RETURNING id",
                (user_id, nombre),
            )
            vaca_id = cur.fetchone()[0]

    return {"output": f"✅ Vaca *{nombre}* creada (ID: {vaca_id}).\nAgrégale gastos cuando quieras, por ejemplo:\n'agregar a vaca {nombre}: fiesta 100000, sonido 20000'"}


# ── Nodo 8: Agregar gastos a vaca ─────────────────────────────────────────

def agregar_vaca(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario puede escribir con errores ortográficos.
    Extrae en JSON:
    {{
      "nombre_vaca": "...",
      "gastos": [{{"descripcion": "...", "monto": ...}}, ...]
    }}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        nombre_vaca = params.get("nombre_vaca", "")
        gastos = params.get("gastos", [])
    except Exception:
        return {"output": "No pude entender. Intenta: 'agregar a vaca Salida: comida 50000'"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            row = _buscar_vaca(cur, user_id, nombre_vaca)
            if not row:
                lista = _listar_vacas(cur, user_id)
                if lista:
                    return {"output": f"No encontré esa vaca. Tus vacas activas son:\n{lista}"}
                return {"output": "No tienes vacas activas. Crea una con 'crear vaca Nombre'"}

            vaca_id = row[0]
            nombre_real = row[1]

            for g in gastos:
                cur.execute(
                    "INSERT INTO vaca_gastos (vaca_id, descripcion, monto) VALUES (%s, %s, %s)",
                    (vaca_id, g.get("descripcion", "gasto"), float(g.get("monto", 0))),
                )

            cur.execute("SELECT COALESCE(SUM(monto),0) FROM vaca_gastos WHERE vaca_id = %s", (vaca_id,))
            total = cur.fetchone()[0]

    desglose = ", ".join([f"{g['descripcion']}: ${int(g['monto']):,}" for g in gastos])
    return {"output": f"✅ Gastos agregados a *{nombre_real}*:\n{desglose}\n\n💰 Total acumulado: ${int(total):,}"}

# ── Nodo 9: Dividir vaca ───────────────────────────────────────────────────

def dividir_vaca(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere dividir una vaca entre personas.
    Extrae en JSON: {{"nombre_vaca": "...", "num_personas": ...}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        nombre_vaca = params.get("nombre_vaca", "")
        num_personas = int(params.get("num_personas", 1))
    except Exception:
        return {"output": "No pude entender. Intenta: 'dividir vaca Salida entre 5 personas'"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre FROM vacas WHERE user_id = %s AND LOWER(nombre) LIKE LOWER(%s) ORDER BY id DESC LIMIT 1",
                (user_id, f"%{nombre_vaca}%"),
            )
            row = cur.fetchone()
            if not row:
                return {"output": f"No encontré la vaca '{nombre_vaca}'."}
            vaca_id, nombre_real = row[0], row[1]

            cur.execute(
                "SELECT descripcion, monto FROM vaca_gastos WHERE vaca_id = %s ORDER BY id",
                (vaca_id,),
            )
            gastos = cur.fetchall()
            total = sum(float(g[1]) for g in gastos)

            cur.execute("UPDATE vacas SET num_personas = %s WHERE id = %s", (num_personas, vaca_id))

    if not gastos:
        return {"output": f"La vaca '{nombre_real}' no tiene gastos registrados."}

    por_persona = total / num_personas
    desglose = "\n".join([f"  • {g[0]}: ${int(g[1]):,}" for g in gastos])

    return {"output": (
        f"📊 *Vaca: {nombre_real}*\n\n"
        f"{desglose}\n\n"
        f"💰 Total: ${int(total):,}\n"
        f"👥 Personas: {num_personas}\n"
        f"➗ Cada uno pone: *${int(por_persona):,}*"
    )}


# ── Nodo 10: Resumen vaca ──────────────────────────────────────────────────

def resumen_vaca(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere ver el resumen de una vaca.
    Extrae en JSON: {{"nombre_vaca": "..."}}
    Si no menciona nombre específico usa: {{"nombre_vaca": "ultima"}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        nombre_vaca = params.get("nombre_vaca", "ultima")
    except Exception:
        nombre_vaca = "ultima"

    with get_conn() as conn:
        with conn.cursor() as cur:
            if nombre_vaca == "ultima":
                cur.execute(
                    "SELECT id, nombre, num_personas FROM vacas WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                    (user_id,),
                )
            else:
                cur.execute(
                    "SELECT id, nombre, num_personas FROM vacas WHERE user_id = %s AND LOWER(nombre) LIKE LOWER(%s) ORDER BY id DESC LIMIT 1",
                    (user_id, f"%{nombre_vaca}%"),
                )
            row = cur.fetchone()
            if not row:
                return {"output": "No encontré ninguna vaca. Crea una con 'crear vaca Nombre'"}
            vaca_id, nombre_real, num_personas = row

            cur.execute(
                "SELECT descripcion, monto FROM vaca_gastos WHERE vaca_id = %s ORDER BY id",
                (vaca_id,),
            )
            gastos = cur.fetchall()
            total = sum(float(g[1]) for g in gastos)

    if not gastos:
        return {"output": f"La vaca *{nombre_real}* no tiene gastos aún."}

    desglose = "\n".join([f"  • {g[0]}: ${int(g[1]):,}" for g in gastos])
    por_persona = f"${int(total/num_personas):,}" if num_personas > 1 else "aún no dividida"

    return {"output": (
        f"📊 *Resumen: {nombre_real}*\n\n"
        f"{desglose}\n\n"
        f"💰 Total: ${int(total):,}\n"
        f"👥 Personas: {num_personas}\n"
        f"➗ Por persona: {por_persona}"
    )}

# ── Nodo 11: Mis Vacas ────────────────────────────────────────────────────────
def mis_vacas(state: dict) -> dict:
    user_id = _validar_user_id(state)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.id, v.nombre, v.num_personas, 
                       COALESCE(SUM(vg.monto), 0) as total
                FROM vacas v
                LEFT JOIN vaca_gastos vg ON v.id = vg.id
                WHERE v.user_id = %s AND v.cerrada = FALSE
                GROUP BY v.id, v.nombre, v.num_personas
                ORDER BY v.id DESC
                """,
                (user_id,),
            )
            vacas = cur.fetchall()

    if not vacas:
        return {"output": "No tienes vacas activas. Crea una con 'crear vaca Nombre' 🐄"}

    lista = "\n".join([
        f"  {i+1}️⃣ *{v[1]}* — Total: ${int(v[3]):,} | 👥 {v[2]} personas"
        for i, v in enumerate(vacas)
    ])

    return {"output": f"🐄 *Tus vacas activas:*\n\n{lista}\n\nPara agregar gastos escribe:\n'agregar vaca [nombre]: item monto'"}

# ── Nodo 12: Registrar deuda ───────────────────────────────────────────────

def registrar_deuda(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere registrar una deuda.
    Extrae en JSON:
    {{
      "tipo": "prestado" (yo le presté a alguien) | "debo" (yo le debo a alguien),
      "persona": "...",
      "monto": ...,
      "descripcion": "..."
    }}
    Texto: "{texto}"
    Fecha hoy: {date.today()}
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
    except Exception:
        return {"output": "No pude entender. Intenta: 'le presté 50000 a Juan para el bus'"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO deudas (user_id, tipo, persona, monto, descripcion) VALUES (%s, %s, %s, %s, %s)",
                (user_id, params.get("tipo"), params.get("persona"), float(params.get("monto", 0)), params.get("descripcion", "")),
            )

    tipo = params.get("tipo")
    persona = params.get("persona")
    monto = int(params.get("monto", 0))
    desc = params.get("descripcion", "")

    if tipo == "prestado":
        return {"output": f"✅ Registrado: *{persona}* te debe ${monto:,}\n📝 {desc}"}
    else:
        return {"output": f"✅ Registrado: le debes ${monto:,} a *{persona}*\n📝 {desc}"}


# ── Nodo 13: Consultar deudas ──────────────────────────────────────────────

def consultar_deudas(state: dict) -> dict:
    user_id = _validar_user_id(state)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tipo, persona, monto, descripcion, fecha FROM deudas WHERE user_id = %s AND pagado = FALSE ORDER BY fecha DESC",
                (user_id,),
            )
            deudas = cur.fetchall()

    if not deudas:
        return {"output": "No tienes deudas pendientes 🎉"}

    prestados = [(p, m, d, f) for t, p, m, d, f in deudas if t == "prestado"]
    debo = [(p, m, d, f) for t, p, m, d, f in deudas if t == "debo"]

    respuesta = "📋 *Deudas pendientes*\n\n"

    if prestados:
        total = sum(float(m) for _, m, _, _ in prestados)
        respuesta += f"💚 *Te deben (total: ${int(total):,})*\n"
        for p, m, d, f in prestados:
            respuesta += f"  • {p}: ${int(m):,} — {d}\n"

    if debo:
        total = sum(float(m) for _, m, _, _ in debo)
        respuesta += f"\n🔴 *Debes (total: ${int(total):,})*\n"
        for p, m, d, f in debo:
            respuesta += f"  • {p}: ${int(m):,} — {d}\n"

    return {"output": respuesta}


# ── Nodo 14: Pagar deuda ───────────────────────────────────────────────────

def pagar_deuda(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere marcar una deuda como pagada.
    Extrae en JSON: {{"persona": "..."}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        persona = params.get("persona", "")
    except Exception:
        return {"output": "No pude entender. Intenta: 'Juan me pagó' o 'pagué a María'"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE deudas SET pagado = TRUE WHERE user_id = %s AND LOWER(persona) LIKE LOWER(%s) AND pagado = FALSE",
                (user_id, f"%{persona}%"),
            )
            filas = cur.rowcount

    if filas:
        return {"output": f"✅ Deuda con *{persona}* marcada como pagada 🎉"}
    else:
        return {"output": f"No encontré deuda pendiente con '{persona}'."}
    
# ── Nodo 15: Registrar ingreso ─────────────────────────────────────────────

def registrar_ingreso(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere registrar un ingreso de dinero.
    Extrae en JSON:
    {{
      "descripcion": "...",
      "monto": ...,
      "fecha": "YYYY-MM-DD"
    }}
    Si no hay fecha usa hoy: {date.today()}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        descripcion = params.get("descripcion", "ingreso")
        monto = float(params.get("monto", 0))
        fecha = params.get("fecha", str(date.today()))
    except Exception:
        return {"output": "No pude entender. Intenta: 'recibí salario 2500000'"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingresos (user_id, descripcion, monto, fecha) VALUES (%s, %s, %s, %s)",
                (user_id, descripcion, monto, fecha),
            )

    return {"output": f"✅ Ingreso registrado\n💵 {descripcion}: ${int(monto):,}\n📅 Fecha: {fecha}"}


# ── Nodo 16: Ver ingresos del mes ──────────────────────────────────────────

def ver_ingresos(state: dict) -> dict:
    user_id = _validar_user_id(state)
    mes = date.today().strftime("%Y-%m")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT descripcion, monto, fecha
                FROM ingresos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                ORDER BY fecha DESC
                """,
                (user_id, mes),
            )
            ingresos = cur.fetchall()
            total = sum(float(i[1]) for i in ingresos)

    if not ingresos:
        return {"output": f"No registraste ingresos en {mes} 📭"}

    detalle = "\n".join([f"  • {i[0]}: ${int(i[1]):,} ({i[2]})" for i in ingresos])
    return {"output": f"💵 *Ingresos de {mes}*\n\n{detalle}\n\n💰 Total: ${int(total):,}"}


# ── Nodo 17: Balance real del mes ──────────────────────────────────────────

def balance_mes(state: dict) -> dict:
    user_id = _validar_user_id(state)
    mes = date.today().strftime("%Y-%m")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(monto), 0) FROM ingresos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                """,
                (user_id, mes),
            )
            total_ingresos = float(cur.fetchone()[0])

            cur.execute(
                """
                SELECT COALESCE(SUM(monto), 0) FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                """,
                (user_id, mes),
            )
            total_gastos = float(cur.fetchone()[0])

    balance = total_ingresos - total_gastos
    emoji = "✅" if balance >= 0 else "🔴"
    estado = "positivo" if balance >= 0 else "negativo"

    return {"output": (
        f"📊 *Balance {mes}*\n\n"
        f"💵 Ingresos:  ${int(total_ingresos):,}\n"
        f"💸 Gastos:    ${int(total_gastos):,}\n"
        f"─────────────────\n"
        f"{emoji} Balance {estado}: ${int(balance):,}"
    )}

# ── Nodo 18: Generar y enviar Excel ───────────────────────────────────────────

def generar_excel(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere un reporte Excel de sus finanzas.
    Extrae en JSON: {{"mes": "YYYY-MM"}}
    Si no menciona mes específico usa el mes actual: {date.today().strftime("%Y-%m")}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        mes = params.get("mes", date.today().strftime("%Y-%m"))
    except Exception:
        mes = date.today().strftime("%Y-%m")

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Gastos
            cur.execute(
                """
                SELECT categoria, monto, fecha
                FROM gastos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                ORDER BY fecha DESC
                """,
                (user_id, mes),
            )
            gastos = cur.fetchall()

            # Ingresos
            cur.execute(
                """
                SELECT descripcion, monto, fecha
                FROM ingresos
                WHERE user_id = %s AND TO_CHAR(fecha, 'YYYY-MM') = %s
                ORDER BY fecha DESC
                """,
                (user_id, mes),
            )
            ingresos = cur.fetchall()

            # Deudas pendientes
            cur.execute(
                """
                SELECT tipo, persona, monto, descripcion, fecha
                FROM deudas
                WHERE user_id = %s AND pagado = FALSE
                ORDER BY fecha DESC
                """,
                (user_id,),
            )
            deudas = cur.fetchall()

            # Vacas
            cur.execute(
                """
                SELECT v.nombre, v.num_personas, 
                       COALESCE(SUM(vg.monto), 0) as total
                FROM vacas v
                LEFT JOIN vaca_gastos vg ON v.id = vg.id
                WHERE v.user_id = %s
                GROUP BY v.id, v.nombre, v.num_personas
                ORDER BY v.fecha_creacion DESC
                """,
                (user_id,),
            )
            vacas = cur.fetchall()

            # Préstamos pendientes
            cur.execute(
                """
                SELECT persona, monto, monto_pagado, tasa_interes, descripcion, fecha, fecha_limite
                FROM prestamos
                WHERE user_id = %s AND pagado = FALSE
                ORDER BY fecha DESC
                """,
                (user_id,),
            )
            prestamos = cur.fetchall()

    # ── Crear Excel ─────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()

    # Estilos
    header_font = Font(bold=True, color="FFFFFF")
    header_fill_green = PatternFill("solid", fgColor="1E7E34")
    header_fill_blue = PatternFill("solid", fgColor="0056B3")
    header_fill_orange = PatternFill("solid", fgColor="D97000")
    header_fill_purple = PatternFill("solid", fgColor="6F42C1")
    center = Alignment(horizontal="center")

    def estilo_header(ws, fila, columnas, fill):
        for col in range(1, columnas + 1):
            cell = ws.cell(row=fila, column=col)
            cell.font = header_font
            cell.fill = fill
            cell.alignment = center

    def autoajustar(ws):
        for col in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = max_len + 4

    # ── Hoja 1: Gastos ──────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = f"Gastos {mes}"
    ws1.append(["Categoría", "Monto", "Fecha"])
    estilo_header(ws1, 1, 3, header_fill_green)

    total_gastos = 0
    for g in gastos:
        ws1.append([g[0], float(g[1]), str(g[2])])
        total_gastos += float(g[1])

    ws1.append([])
    ws1.append(["TOTAL", total_gastos, ""])
    total_row = ws1.max_row
    ws1.cell(total_row, 1).font = Font(bold=True)
    ws1.cell(total_row, 2).font = Font(bold=True)
    autoajustar(ws1)

    # ── Hoja 2: Ingresos ────────────────────────────────────────────────────
    ws2 = wb.create_sheet(f"Ingresos {mes}")
    ws2.append(["Descripción", "Monto", "Fecha"])
    estilo_header(ws2, 1, 3, header_fill_blue)

    total_ingresos = 0
    for i in ingresos:
        ws2.append([i[0], float(i[1]), str(i[2])])
        total_ingresos += float(i[1])

    ws2.append([])
    ws2.append(["TOTAL", total_ingresos, ""])
    total_row = ws2.max_row
    ws2.cell(total_row, 1).font = Font(bold=True)
    ws2.cell(total_row, 2).font = Font(bold=True)
    autoajustar(ws2)

    # ── Hoja 3: Deudas y Vacas ──────────────────────────────────────────────
    ws3 = wb.create_sheet("Deudas y Vacas")
    ws3.append(["DEUDAS PENDIENTES", "", "", "", ""])
    ws3.cell(1, 1).font = Font(bold=True, size=12)
    ws3.append(["Tipo", "Persona", "Monto", "Descripción", "Fecha"])
    estilo_header(ws3, 2, 5, header_fill_orange)

    for d in deudas:
        tipo = "Me deben" if d[0] == "prestado" else "Debo"
        ws3.append([tipo, d[1], float(d[2]), d[3], str(d[4])])

    ws3.append([])
    ws3.append(["VACAS GRUPALES", "", ""])
    ws3.cell(ws3.max_row, 1).font = Font(bold=True, size=12)
    ws3.append(["Nombre", "Personas", "Total"])
    estilo_header(ws3, ws3.max_row, 3, header_fill_purple)

    for v in vacas:
        por_persona = float(v[2]) / v[1] if v[1] > 0 else 0
        ws3.append([v[0], v[1], float(v[2])])

    autoajustar(ws3)

    # ── Hoja 4: Préstamos ───────────────────────────────────────────────────
    header_fill_teal = PatternFill("solid", fgColor="0097A7")
    ws_p = wb.create_sheet("Préstamos")
    ws_p.append(["Persona", "Monto", "Abonado", "Pendiente", "Interés %", "Descripción", "Fecha", "Vence"])
    estilo_header(ws_p, 1, 8, header_fill_teal)

    total_prestado = 0
    for p in prestamos:
        persona, monto, pagado, tasa, desc, fecha, limite = p
        monto = float(monto)
        pagado = float(pagado)
        pendiente = monto - pagado
        total_prestado += pendiente
        ws_p.append([
            persona,
            monto,
            pagado,
            pendiente,
            float(tasa),
            desc,
            str(fecha),
            str(limite) if limite else "Sin fecha",
        ])

    ws_p.append([])
    ws_p.append(["TOTAL PENDIENTE", "", "", total_prestado, "", "", "", ""])
    total_row = ws_p.max_row
    ws_p.cell(total_row, 1).font = Font(bold=True)
    ws_p.cell(total_row, 4).font = Font(bold=True)
    autoajustar(ws_p)

    # ── Hoja 5: Resumen ─────────────────────────────────────────────────────
    ws4 = wb.create_sheet("Resumen")
    balance = total_ingresos - total_gastos
    estado = "✅ Positivo" if balance >= 0 else "🔴 Negativo"

    ws4.append(["RESUMEN FINANCIERO", mes])
    ws4.cell(1, 1).font = Font(bold=True, size=14)
    ws4.append([])
    ws4.append(["Concepto", "Monto"])
    estilo_header(ws4, 3, 2, header_fill_blue)
    ws4.append(["Total Ingresos", total_ingresos])
    ws4.append(["Total Gastos", total_gastos])
    ws4.append(["Balance", balance])
    ws4.append(["Estado", estado])
    ws4.append([])
    ws4.append(["Deudas pendientes", len(deudas)])
    ws4.append(["Vacas activas", len(vacas)])
    ws4.append(["Total prestado pendiente", total_prestado])

    ws4.cell(6, 1).font = Font(bold=True)
    ws4.cell(6, 2).font = Font(bold=True, color="1E7E34" if balance >= 0 else "DC3545")
    autoajustar(ws4)

    # ── Guardar en memoria y devolver ───────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return {
        "output": f"📊 Reporte Excel de {mes} listo.",
        "excel_buffer": buffer,
        "excel_nombre": f"finanzas_{mes}.xlsx"
    }

# ── Nodo 19: Registrar préstamo ────────────────────────────────────────────

def registrar_prestamo(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario prestó dinero a alguien.
    Extrae en JSON:
    {{
      "persona": "...",
      "monto": ...,
      "descripcion": "...",
      "tasa_interes": ... (número % mensual, 0 si no menciona interés),
      "fecha_limite": "YYYY-MM-DD" (null si no menciona fecha límite)
    }}
    Fecha hoy: {date.today()}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={{"type": "json_object"}},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
    except Exception:
        return {{"output": "No pude entender. Intenta: 'le presté 200000 a Carlos para el arriendo'"}}

    persona = params.get("persona", "")
    monto = float(params.get("monto", 0))
    descripcion = params.get("descripcion", "")
    tasa = float(params.get("tasa_interes", 0))
    fecha_limite = params.get("fecha_limite")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO prestamos (user_id, persona, monto, descripcion, tasa_interes, fecha_limite)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, persona, monto, descripcion, tasa, fecha_limite),
            )

    interes_msg = f" con {tasa}% de interés mensual" if tasa > 0 else " sin interés"
    limite_msg = f"\n📅 Fecha límite: {fecha_limite}" if fecha_limite else ""
    return {{"output": (
        f"✅ Préstamo registrado\n"
        f"👤 Prestado a: *{persona}*\n"
        f"💵 Monto: ${int(monto):,}{interes_msg}\n"
        f"📝 {descripcion}{limite_msg}"
    )}}


# ── Nodo 20: Ver préstamos pendientes ──────────────────────────────────────

def ver_prestamos(state: dict) -> dict:
    user_id = _validar_user_id(state)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT persona, monto, monto_pagado, tasa_interes, descripcion, fecha, fecha_limite
                FROM prestamos
                WHERE user_id = %s AND pagado = FALSE
                ORDER BY fecha DESC
                """,
                (user_id,),
            )
            prestamos = cur.fetchall()

    if not prestamos:
        return {{"output": "No tienes préstamos pendientes por cobrar 🎉"}}

    respuesta = "💰 *Préstamos pendientes por cobrar*\n\n"
    total = 0

    for p in prestamos:
        persona, monto, pagado, tasa, desc, fecha, limite = p
        monto = float(monto)
        pagado = float(pagado)
        pendiente = monto - pagado

        # Calcular interés acumulado si aplica
        if tasa > 0:
            from datetime import date as d_
            meses = max(1, (d_.today() - fecha).days // 30)
            interes = monto * (tasa / 100) * meses
            total_con_interes = pendiente + interes
            interes_str = f" (+${int(interes):,} interés acum.)"
        else:
            total_con_interes = pendiente
            interes_str = ""

        total += total_con_interes
        limite_str = f" | vence {limite}" if limite else ""
        abono_str = f" | abonado: ${int(pagado):,}" if pagado > 0 else ""

        respuesta += (
            f"👤 *{persona}*: ${int(pendiente):,}{interes_str}{abono_str}{limite_str}\n"
            f"   📝 {desc}\n\n"
        )

    respuesta += f"💵 *Total por cobrar: ${int(total):,}*"
    return {{"output": respuesta}}


# ── Nodo 21: Registrar abono a préstamo ───────────────────────────────────

def abonar_prestamo(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere registrar un abono a un préstamo que hizo.
    Extrae en JSON: {{"persona": "...", "monto_abono": ...}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={{"type": "json_object"}},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        persona = params.get("persona", "")
        abono = float(params.get("monto_abono", 0))
    except Exception:
        return {{"output": "No pude entender. Intenta: 'Carlos me abonó 50000'"}}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, monto, monto_pagado FROM prestamos
                WHERE user_id = %s AND LOWER(persona) LIKE LOWER(%s) AND pagado = FALSE
                ORDER BY id DESC LIMIT 1
                """,
                (user_id, f"%{persona}%"),
            )
            row = cur.fetchone()
            if not row:
                return {{"output": f"No encontré préstamo pendiente con '{persona}'."}}

            prestamo_id = row[0]
            monto_total = float(row[1])
            ya_pagado = float(row[2])
            nuevo_pagado = ya_pagado + abono
            pendiente = monto_total - nuevo_pagado

            if nuevo_pagado >= monto_total:
                cur.execute(
                    "UPDATE prestamos SET monto_pagado = %s, pagado = TRUE WHERE id = %s",
                    (nuevo_pagado, prestamo_id),
                )
                return {{"output": f"✅ *{persona}* pagó el préstamo completo 🎉\n💵 Total recibido: ${int(nuevo_pagado):,}"}}
            else:
                cur.execute(
                    "UPDATE prestamos SET monto_pagado = %s WHERE id = %s",
                    (nuevo_pagado, prestamo_id),
                )

    return {{"output": (
        f"✅ Abono registrado de *{persona}*\n"
        f"💵 Abono: ${int(abono):,}\n"
        f"✔️ Total pagado: ${int(nuevo_pagado):,}\n"
        f"⏳ Pendiente: ${int(pendiente):,}"
    )}}


# ── Nodo 22: Marcar préstamo como pagado ───────────────────────────────────

def cerrar_prestamo(state: dict) -> dict:
    user_id = _validar_user_id(state)
    texto = state["input"]

    prompt = f"""
    El usuario quiere marcar un préstamo como completamente pagado.
    Extrae en JSON: {{"persona": "..."}}
    Texto: "{texto}"
    """
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": prompt}],
        response_format={{"type": "json_object"}},
    )
    try:
        params = json.loads(resp.choices[0].message.content)
        persona = params.get("persona", "")
    except Exception:
        return {{"output": "No pude entender. Intenta: 'Carlos pagó todo'"}}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE prestamos SET pagado = TRUE
                WHERE user_id = %s AND LOWER(persona) LIKE LOWER(%s) AND pagado = FALSE
                """,
                (user_id, f"%{persona}%"),
            )
            filas = cur.rowcount

    if filas:
        return {{"output": f"✅ Préstamo con *{persona}* cerrado como pagado completo 🎉"}}
    else:
        return {{"output": f"No encontré préstamo pendiente con '{persona}'."}}