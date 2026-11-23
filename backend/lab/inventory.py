import time
from typing import Annotated

from fastapi import FastAPI, Query

app = FastAPI(title="Synthetic inventory dependency")


@app.get("/stock")
def stock(region: str = "healthy", delay_ms: Annotated[int, Query(ge=0, le=400)] = 0):
    from fastapi.responses import JSONResponse

    if delay_ms:
        time.sleep(delay_ms / 1000)
    return JSONResponse(
        {"available": True}
        if region == "healthy"
        else {"error": "Region is not configured"},
        status_code=200 if region == "healthy" else 503,
    )
