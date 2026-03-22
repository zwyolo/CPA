from fastapi import FastAPI
from mcp_server import mcp

app = FastAPI()

@app.get("/")
def health():
    return {"status": "running"}

# 版本 2：试这个
mcp_app = mcp.http_app()
app.mount("/mcp", mcp_app)