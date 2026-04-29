from fastapi import FastAPI

from app.api import catalog, corrections, health, jobs
from app.dashboard import routes as dashboard_routes

app = FastAPI(title="HeyRoya Automation API")
app.include_router(health.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(corrections.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(dashboard_routes.router)
