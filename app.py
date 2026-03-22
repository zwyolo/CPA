from fastapi import FastAPI
from mcp_server import mcp

app = FastAPI()


@app.get("/")
def health():
    return {"status": "running"}


app.mount("/CPA/mcp", mcp.streamable_http_app())
