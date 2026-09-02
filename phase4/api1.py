from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from phase4.api1_models import NetworkSummaryResponse
from phase4.api1_service import get_network_summary
from phase4.api2_grillact import router as api2_router
from phase4.api3_hotspotandalert import router as api3_router
from phase4.api6_opsupp import router as api6_router
from phase4.api5_prediction import router as api5_router

app = FastAPI(
    title="Milestone 1 Network Intelligence API",
    version="1.0.0",
    description="Network intelligence analytics API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok"}

@app.get(
    "/network/summary",
    response_model=NetworkSummaryResponse,
    summary="Network summary",
)
def network_summary(
    as_of: str | None = Query(
        default=None,
        description=(
            "Optional ISO-8601 reporting timestamp. "
            "Defaults to the maximum timestamp in the analytics layer."
        ),
    ),
) -> NetworkSummaryResponse:

    try:
        return get_network_summary(as_of)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Network analytics data source unavailable: {exc}",
        ) from exc

app.include_router(api2_router)
app.include_router(api3_router)
app.include_router(api5_router)
app.include_router(api6_router)