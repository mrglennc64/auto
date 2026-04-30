from fastapi import FastAPI

from app.api import catalog, corrections, health, jobs, portal
from app.dashboard import routes as dashboard_routes

app = FastAPI(title="HeyRoya Automation API")
app.include_router(health.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(corrections.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(dashboard_routes.router)
# Portal router is included LAST. Its catch-all GET routes only fire when
# the request Host matches a configured tenant — otherwise it returns 404.
# This keeps /api and /dashboard working on automation.heyroya.se.
app.include_router(portal.router)
