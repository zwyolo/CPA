from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp_server import mcp

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health():
    return {"status": "running"}

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

app.mount("/mcp", mcp.streamable_http_app())