from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from database import connect_to_mongo, close_mongo_connection
from routes import auth, stories, comments, chapters, videos, monitoring, users, shots
from config import get_settings
import os
import logging
import time
from pathlib import Path
from logger_config import setup_logging
from middleware import RequestLoggingMiddleware, PerformanceMonitoringMiddleware, ErrorTrackingMiddleware
from metrics import metrics_collector

settings = get_settings()

# Setup logging
logger = setup_logging(log_level="INFO", log_dir="logs")
logger.info("Application starting...")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute", "1000/hour"])

app = FastAPI(
    title="Wattpad Clone API",
    description="A full-stack blogging application with JWT authentication",
    version="1.0.0"
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add custom middleware (order matters - first added is outermost)
app.add_middleware(ErrorTrackingMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory if it doesn't exist
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

# Mount static files for uploads
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# Include routers
app.include_router(auth.router)
app.include_router(stories.router)
app.include_router(comments.router)
app.include_router(chapters.router)
app.include_router(videos.router)
app.include_router(monitoring.router)
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(shots.router, prefix="/api/shots", tags=["shots"])

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Connecting to MongoDB...")
    await connect_to_mongo()
    logger.info("Application started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    await close_mongo_connection()
    logger.info("Application shutdown complete")

# Middleware to collect metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Try to extract user ID from JWT token
    user_id = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            from jose import jwt
            from config import get_settings
            settings = get_settings()
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            username = payload.get("sub")
            if username:
                # Use username as user_id for tracking
                user_id = username
        except Exception:
            pass  # Ignore token parsing errors for metrics
    
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Record metrics with user_id
    metrics_collector.record_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration,
        user_id=user_id
    )
    
    return response

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to Wattpad Clone API",
        "version": "1.0.0",
        "docs": "/docs"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}: {str(exc)}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
