from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.router import router, decidir_nodo
from agent.nodes import (
    guardar_gasto, reporte_dia, reporte_mes,
    reporte_categoria, editar_gasto, presupuesto,
    crear_vaca, agregar_vaca, dividir_vaca, resumen_vaca,
    registrar_deuda, consultar_deudas, pagar_deuda,
    registrar_ingreso, ver_ingresos, balance_mes,
    generar_excel, mis_vacas
)

graph = StateGraph(AgentState)

graph.add_node("router",             router)
graph.add_node("guardar",            guardar_gasto)
graph.add_node("reporte_dia",        reporte_dia)
graph.add_node("reporte_mes",        reporte_mes)
graph.add_node("reporte_categoria",  reporte_categoria)
graph.add_node("editar",             editar_gasto)
graph.add_node("presupuesto",        presupuesto)
graph.add_node("crear_vaca",         crear_vaca)
graph.add_node("agregar_vaca",       agregar_vaca)
graph.add_node("dividir_vaca",       dividir_vaca)
graph.add_node("resumen_vaca",       resumen_vaca)
graph.add_node("registrar_deuda",    registrar_deuda)
graph.add_node("consultar_deudas",   consultar_deudas)
graph.add_node("pagar_deuda",        pagar_deuda)
graph.add_node("registrar_ingreso",  registrar_ingreso)
graph.add_node("ver_ingresos",       ver_ingresos)
graph.add_node("balance_mes",        balance_mes)
graph.add_node("generar_excel",     generar_excel)
graph.add_node("mis_vacas",         mis_vacas)

graph.set_entry_point("router")

graph.add_conditional_edges(
    "router",
    decidir_nodo,
    {
        "guardar":            "guardar",
        "reporte_dia":        "reporte_dia",
        "reporte_mes":        "reporte_mes",
        "reporte_categoria":  "reporte_categoria",
        "editar":             "editar",
        "presupuesto":        "presupuesto",
        "crear_vaca":         "crear_vaca",
        "agregar_vaca":       "agregar_vaca",
        "dividir_vaca":       "dividir_vaca",
        "resumen_vaca":       "resumen_vaca",
        "registrar_deuda":    "registrar_deuda",
        "consultar_deudas":   "consultar_deudas",
        "pagar_deuda":        "pagar_deuda",
        "registrar_ingreso":  "registrar_ingreso",
        "ver_ingresos":       "ver_ingresos",
        "balance_mes":        "balance_mes",
        "generar_excel":      "generar_excel",
        "mis_vacas":         "mis_vacas",
    }
)

todos_los_nodos = [
    "guardar", "reporte_dia", "reporte_mes", "reporte_categoria",
    "editar", "presupuesto", "crear_vaca", "agregar_vaca",
    "dividir_vaca", "resumen_vaca", "registrar_deuda",
    "consultar_deudas", "pagar_deuda", "registrar_ingreso",
    "ver_ingresos", "balance_mes", "generar_excel", "mis_vacas"
]
for nodo in todos_los_nodos:
    graph.add_edge(nodo, END)

app = graph.compile()