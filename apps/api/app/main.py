from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, documents, fees, importer, intel, messages, office, planner, records, share, team, workspace
from .api.routes import router
from .config import get_settings

settings = get_settings()
settings.check_production()
app = FastAPI(title=f"{settings.product_name} API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(office.router, prefix="/api")

for _r in (team, workspace, importer, planner, documents, records, messages, intel, fees, share):
    app.include_router(_r.router, prefix="/api")
