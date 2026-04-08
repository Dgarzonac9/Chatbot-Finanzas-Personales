from dotenv import load_dotenv
from groq import Groq
import os, json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODELO_LLM = os.getenv("MODELO_LLM")

PROMPT_ROUTER = """
Clasifica el mensaje del usuario en UNA de estas intenciones:
- guardar: quiere registrar un gasto personal
- reporte_dia: quiere saber cuánto gastó hoy
- reporte_mes: quiere saber cuánto gastó este mes
- reporte_categoria: quiere ver gastos por categoría
- editar: quiere eliminar o corregir un gasto
- presupuesto: quiere establecer o consultar su presupuesto
- crear_vaca: quiere crear una vaca o fondo grupal para un evento
- agregar_vaca: quiere agregar gastos a una vaca existente
- dividir_vaca: quiere dividir el total de una vaca entre personas
- resumen_vaca: quiere ver el resumen o detalle de una vaca
- registrar_deuda: quiere registrar que le prestó dinero a alguien o que él debe dinero
- consultar_deudas: quiere ver quién le debe o a quién le debe
- pagar_deuda: quiere marcar una deuda como pagada

Responde SOLO en JSON: {{"intencion": "..."}}

Mensaje: "{mensaje}"
"""

def router(state: dict) -> dict:
    resp = client.chat.completions.create(
        model=MODELO_LLM,
        messages=[{"role": "user", "content": PROMPT_ROUTER.format(mensaje=state["input"])}],
        response_format={"type": "json_object"}
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        intencion = data.get("intencion", "guardar")
    except Exception:
        intencion = "guardar"

    print(f"[Router] Intención: {intencion}")
    return {"intencion": intencion}


def decidir_nodo(state: dict) -> str:
    return state.get("intencion", "guardar")