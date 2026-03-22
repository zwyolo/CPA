from fastapi import FastAPI
from mcp_server import mcp

app = FastAPI()

@app.get("/")
def health():
    return {"status": "running"}

mcp_app = mcp.streamable_http_app()
app.mount("/mcp", mcp_app)

@app.get("/routes")
def routes():
    return [
        {
            "path": getattr(route, "path", str(route)),
            "name": getattr(route, "name", None),
            "methods": list(getattr(route, "methods", []) or []),
        }
        for route in app.routes
    ]