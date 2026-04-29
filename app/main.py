from fastapi import FastAPI

from app.api import health

app = FastAPI(title="HeyRoya Automation API")
app.include_router(health.router, prefix="/api")
