from typing import TypedDict, Optional

class AgentState(TypedDict):
    input: str
    user_id: int
    intencion: Optional[str]   # "guardar", "reporte_dia", "reporte_mes",
                                # "reporte_categoria", "editar", "presupuesto"
    output: Optional[str]