from dotenv import load_dotenv
from groq import Groq
import os, json

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
MODELO_LLM = os.getenv("MODELO_LLM")

client = Groq(api_key=API_KEY)

PROMPT_ROUTER = """
Clasifica el mensaje del usuario en UNA de estas intenciones:
- guardar: quiere registrar un gasto
- reporte_dia: quiere saber cuánto gastó hoy
- reporte_mes: quiere saber cuánto gastó este mes
- reporte_categoria: quiere ver gastos por categoría
- editar: quiere eliminar o corregir un gasto
- presupuesto: quiere establecer o consultar su presupuesto

Responde SOLO en JSON: {{"intencion": "..."}}

Mensaje: "{mensaje}"
"""

def router(state: dict) -> dict:
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": PROMPT_ROUTER.format(
            mensaje=state["input"]
        )}],
        response_format={"type": "json_object"}
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        intencion = data.get("intencion", "guardar")
    except Exception:
        intencion = "guardar"

    print(f"[Router] Intención detectada: {intencion}")
    return {"intencion": intencion}


def decidir_nodo(state: dict) -> str:
    """LangGraph usa esta función para el conditional_edge."""
    return state.get("intencion", "guardar")