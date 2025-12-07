import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
from typing import Callable
import json

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = f"{int(time.time() * 1000)}"
        
        # Log request details
        logger.info(
            f"Request [{request_id}]: {request.method} {request.url.path} "
            f"- Client: {request.client.host if request.client else 'unknown'}"
        )
        
        # Log request headers (excluding sensitive data)
        safe_headers = {
            k: v for k, v in request.headers.items() 
            if k.lower() not in ['authorization', 'cookie']
        }
        logger.debug(f"Request [{request_id}] Headers: {safe_headers}")
        
        # Start timing
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Calculate request duration
            duration = time.time() - start_time
            
            # Log response
            logger.info(
                f"Response [{request_id}]: {response.status_code} - "
                f"Duration: {duration:.3f}s"
            )
            
            # Add custom headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(duration)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Request [{request_id}] failed after {duration:.3f}s: {str(e)}",
                exc_info=True
            )
            raise


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor slow requests"""
    
    SLOW_REQUEST_THRESHOLD = 1.0  # seconds
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Log slow requests
        if duration > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} "
                f"took {duration:.3f}s (threshold: {self.SLOW_REQUEST_THRESHOLD}s)"
            )
        
        return response


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track and log errors"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            
            # Log 4xx and 5xx responses
            if response.status_code >= 400:
                logger.warning(
                    f"Error response: {request.method} {request.url.path} "
                    f"returned {response.status_code}"
                )
            
            return response
            
        except Exception as e:
            logger.error(
                f"Unhandled exception in {request.method} {request.url.path}: {str(e)}",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else "unknown"
                }
            )
            raise
