from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import logging
from auth import get_current_user
from models import UserRole
from metrics import metrics_collector
from database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require admin role for monitoring endpoints"""
    if current_user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return current_user


@router.get("/metrics")
async def get_metrics(
    current_user: dict = Depends(require_admin),
    db = Depends(get_database)
):
    """Get application metrics (admin only)"""
    metrics = metrics_collector.get_metrics_summary()
    user_stats = metrics_collector.get_user_stats()
    
    # Get total registered users from database
    try:
        total_registered_users = await db.users.count_documents({})
    except Exception as e:
        logger.error(f"Error counting users: {str(e)}")
        total_registered_users = 0
    
    return {
        **metrics,
        **user_stats,
        'total_registered_users': total_registered_users
    }


@router.get("/metrics/errors")
async def get_recent_errors(
    limit: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(require_admin)
):
    """Get recent error requests (admin only)"""
    return {"errors": metrics_collector.get_recent_errors(limit=limit)}


@router.get("/metrics/reset")
async def reset_metrics(current_user: dict = Depends(require_admin)):
    """Reset all metrics (admin only)"""
    metrics_collector.reset()
    return {"message": "Metrics reset successfully"}


@router.get("/logs")
async def get_logs(
    log_type: str = Query("app", regex="^(app|error)$"),
    lines: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(require_admin)
):
    """Get recent log entries (admin only)"""
    try:
        log_dir = Path("logs")
        
        # Find the most recent log file
        if log_type == "app":
            pattern = "app_*.log"
        else:
            pattern = "error_*.log"
        
        log_files = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not log_files:
            return {
                "log_type": log_type,
                "lines": [],
                "message": "No log files found"
            }
        
        # Read the most recent log file
        log_file = log_files[0]
        
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # Get last N lines
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "log_type": log_type,
            "log_file": log_file.name,
            "total_lines": len(all_lines),
            "lines": [line.strip() for line in recent_lines]
        }
        
    except Exception as e:
        logger.error(f"Error reading logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read logs: {str(e)}"
        )


@router.get("/logs/search")
async def search_logs(
    query: str = Query(..., min_length=1),
    log_type: str = Query("app", regex="^(app|error)$"),
    max_results: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_admin)
):
    """Search log entries (admin only)"""
    try:
        log_dir = Path("logs")
        
        if log_type == "app":
            pattern = "app_*.log"
        else:
            pattern = "error_*.log"
        
        log_files = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not log_files:
            return {
                "query": query,
                "log_type": log_type,
                "results": [],
                "message": "No log files found"
            }
        
        results = []
        query_lower = query.lower()
        
        # Search through log files (most recent first)
        for log_file in log_files:
            if len(results) >= max_results:
                break
                
            with open(log_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if query_lower in line.lower():
                        results.append({
                            "file": log_file.name,
                            "line_number": line_num,
                            "content": line.strip()
                        })
                        
                        if len(results) >= max_results:
                            break
        
        return {
            "query": query,
            "log_type": log_type,
            "total_results": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error searching logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search logs: {str(e)}"
        )


@router.get("/health")
async def get_health_status(current_user: dict = Depends(require_admin)):
    """Get application health status (admin only)"""
    try:
        from database import get_database
        
        # Check database connection
        db = await get_database().__anext__()
        await db.command("ping")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "unhealthy"
    
    # Check logs directory
    logs_dir = Path("logs")
    logs_status = "healthy" if logs_dir.exists() and logs_dir.is_dir() else "unhealthy"
    
    # Check uploads directory
    uploads_dir = Path("uploads")
    uploads_status = "healthy" if uploads_dir.exists() and uploads_dir.is_dir() else "unhealthy"
    
    overall_status = "healthy" if all([
        db_status == "healthy",
        logs_status == "healthy",
        uploads_status == "healthy"
    ]) else "degraded"
    
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": db_status,
            "logs": logs_status,
            "uploads": uploads_status
        }
    }
