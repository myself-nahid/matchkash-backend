import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings

# Run migrations using subprocess
def run_migrations():
    """Run alembic upgrade head as a separate process"""
    try:
        print("Checking for database migrations...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Database migrations applied successfully.")
    except Exception as e:
        print(f"Error applying migrations: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend for Sports Prediction App",
    version="1.0.0",
    lifespan=lifespan 
)

# CORS (Allow Flutter App)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded files as static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Welcome to MatchKash API"}