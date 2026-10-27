import logging

from fastapi import FastAPI

from app.middleware.error_handler import register_error_handlers
from app.routes.plans_routes import router as plans_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HealthCare Plans API")


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(plans_router, prefix="/api/v1/plans")
register_error_handlers(app)
