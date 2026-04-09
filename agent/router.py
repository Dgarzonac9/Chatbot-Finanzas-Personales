from dotenv import load_dotenv
from groq import Groq
import os, json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODELO_LLM = os.getenv("MODELO_LLM")

PROMPT_ROUTER = """
Eres un clasificador de intenciones para un chatbot de finanzas personales.
El usuario puede escribir con errores ortográficos, abreviaciones o de forma informal.
Debes inferir la intención aunque el mensaje esté mal escrito.

Clasifica en UNA de estas intenciones:
- guardar: registrar un gasto o compra ("gaste", "compre", "pague", "me costo")
- reporte_dia: gastos de hoy ("cuanto gaste hoy", "resumen hoy", "q gaste")
- reporte_mes: gastos del mes ("este mes", "del mes", "mensual")
- reporte_categoria: gastos por categoría ("por categoria", "en que gaste mas")
- editar: eliminar o corregir gasto ("borra", "elimina", "quita", "me equivoque")
- presupuesto: presupuesto mensual ("presupuesto", "limite", "cuanto puedo gastar")
- crear_vaca: crear fondo grupal ("vaca", "fondo", "juntar plata", "pool")
- agregar_vaca: agregar gastos a vaca ("agregar a vaca", "añadir a vaca", "gasto vaca")
- dividir_vaca: dividir vaca entre personas ("dividir", "cuanto pone cada uno", "split")
- resumen_vaca: ver resumen de vaca ("resumen vaca", "como va la vaca", "ver vaca")
- mis_vacas: listar todas las vacas ("mis vacas", "que vacas tengo", "vacas activas")
- registrar_deuda: deudas informales sin seguimiento de abonos ("le debo", "me debe", "me presto alguien a mi")
- consultar_deudas: ver deudas ("quien me debe", "mis deudas", "deudas pendientes")
- pagar_deuda: marcar deuda pagada ("me pago", "ya pague", "saldo deuda")
- registrar_ingreso: registrar ingreso ("recibi", "me pagaron", "salario", "ingreso")
- ver_ingresos: ver ingresos ("mis ingresos", "cuanto recibi")
- balance_mes: balance ingresos vs gastos ("balance", "como voy", "cuanto me queda")
- generar_excel: reporte en Excel ("excel", "reporte", "exportar", "descargar")
- registrar_prestamo: yo presté dinero y quiero hacer seguimiento con abonos e interés ("yo le preste", "le di un prestamo formal", "con interes")- ver_prestamos: ver préstamos que hice ("mis prestamos", "quien me debe prestamo", "prestamos pendientes")
- abonar_prestamo: registrar un pago parcial de un préstamo ("me abono", "me dio un abono", "pago algo")
- cerrar_prestamo: marcar préstamo como pagado completo ("pago todo", "saldo completo", "termino de pagar")

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