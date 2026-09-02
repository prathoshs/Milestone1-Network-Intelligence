from pydantic import BaseModel

class NetworkSummaryResponse(BaseModel):
    total_activity: float
    active_grids: int
    peak_hour: str
    top_grid: str
    as_of: str