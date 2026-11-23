from fastapi import FastAPI

app = FastAPI(title="Synthetic inventory dependency")


@app.get("/stock")
def stock(region: str = "healthy"):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        {"available": True}
        if region == "healthy"
        else {"error": "Region is not configured"},
        status_code=200 if region == "healthy" else 503,
    )
