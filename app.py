from fastapi import FastAPI
from mcp_server import mcp

app = FastAPI()

@app.get("/")
def health():
    return {"status": "running"}

app.mount("/mcp", mcp.streamable_http_app())