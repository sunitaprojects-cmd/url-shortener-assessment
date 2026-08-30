from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import redirect_router, router
from app.config import Settings
from app.database import Database


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings.from_environment()
    app.state.database = Database(app.state.settings.database_url)
    try:
        yield
    finally:
        app.state.database.dispose()


app = FastAPI(title="URL Shortener Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(redirect_router)
