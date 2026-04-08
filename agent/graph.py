from langgraph.graph import StateGraph
from agent.state import AgentState
from agent.router import router, decidir_nodo
from agent.nodes import (
    guardar_gasto, reporte_dia, reporte_mes,
    reporte_categoria, editar_gasto, presupuesto
)

graph = StateGraph(AgentState)

# Nodos
graph.add_node("router",            router)
graph.add_node("guardar",           guardar_gasto)
graph.add_node("reporte_dia",       reporte_dia)
graph.add_node("reporte_mes",       reporte_mes)
graph.add_node("reporte_categoria", reporte_categoria)
graph.add_node("editar",            editar_gasto)
graph.add_node("presupuesto",       presupuesto)

# Entrada → router
graph.set_entry_point("router")

# Router → nodo correspondiente (conditional edge)
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
    }
)

# Todos los nodos terminan en END
from langgraph.graph import END
for nodo in ["guardar", "reporte_dia", "reporte_mes",
             "reporte_categoria", "editar", "presupuesto"]:
    graph.add_edge(nodo, END)

app = graph.compile()