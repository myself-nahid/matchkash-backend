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
    import sys
    import os
    try:
        print("Checking for database migrations...")
        # Get the directory of the current python executable
        executable_path = sys.executable
        executable_dir = os.path.dirname(executable_path)
        
        # In Windows it is Scripts, in Linux/Mac it is bin
        alembic_cmd = os.path.join(executable_dir, "alembic")
        if os.name == 'nt': # Windows
            alembic_cmd += ".exe"
            
        if os.path.exists(alembic_cmd):
            subprocess.run([alembic_cmd, "upgrade", "head"], check=True)
        else:
            # Fallback to simple command if not found in same dir
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

origins = [
    "http://localhost:3000",
    "http://10.10.12.70:3001",  
    "http://10.10.12.70:3000",
    "http://10.10.12.11:3000",
    "https://xentra-admin-dashboard.vercel.app/",
    "https://xentra-admin-dashboard.vercel.app"
]

# CORS (Allow Flutter App)
app.add_middleware(
    CORSMiddleware,
    allow_origins= origins, 
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