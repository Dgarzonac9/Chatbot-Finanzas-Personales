from typing import TypedDict, Optional
import io

class AgentState(TypedDict):
    input: str
    user_id: int
    intencion: Optional[str]
    output: Optional[str]
    excel_buffer: Optional[io.BytesIO]
    excel_nombre: Optional[str]