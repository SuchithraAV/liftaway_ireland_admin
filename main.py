from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from core.database import engine, Base
from core.redis_client import redis_pool
from core.routers import services, bookings, driver, admin, payments
from core.routers import stripe_payments
from core.routers.profile import router as profile
from core.routers.auth_api import router as auth_api
from core.routers.driver_registration import router as driver_registration_router
from core.routers.issues import router as issues_router, driver_router as issues_driver_router
from core.routers.location_ws import router as location_ws_router
from core.routers.driver_ratings import router as driver_ratings_router
from core.routers.chat import router as chat_router
from core.routers.notifications import router as notifications_router
from core.routers.driver_wallet import router as driver_wallet_router
from core.routers.driver_stripe_setup import router as driver_stripe_setup_router
from core.routers.stripe_connect_webhook import router as stripe_connect_webhook_router
from core.routers.platform_balance import router as platform_balance_router
from core.notifications_websocket import notifications_manager
# from core.routers.email_verification import router as email_verification
from core.websocket import manager
from config import settings
import logging
import traceback
from datetime import datetime

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Initialize Redis connection pool
    await redis_pool.initialize()
    
    # Start notifications Redis subscriber using configured Redis URL
    await notifications_manager.start_subscriber(settings.REDIS_URL)
    
    yield
    
    # Shutdown
    await notifications_manager.stop_subscriber()
    await redis_pool.close()
    await engine.dispose()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=f"{settings.PROJECT_NAME} - Driver/Admin API",
    version=settings.VERSION,
    lifespan=lifespan,
    debug=False  # Production mode - custom exception handlers provide error details
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Exception handlers - these will catch errors and return them in API responses
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    error_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    error_details = {
        "error_id": error_id,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "path": str(request.url),
        "method": request.method,
        "timestamp": datetime.now().isoformat()
    }
    
    # Log to console with full traceback
    logger.error(f"Error {error_id}: {error_details}")
    logger.error(f"Full traceback:\n{traceback.format_exc()}")
    
    # Return error in API response
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": error_details,
            "message": "An internal server error occurred. Check logs for details."
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    error_details = {
        "error_type": "HTTPException",
        "status_code": exc.status_code,
        "error_message": exc.detail,
        "path": str(request.url),
        "method": request.method,
        "timestamp": datetime.now().isoformat()
    }
    
    # Log to console
    logger.warning(f"HTTP Exception: {error_details}")
    
    # Return error in API response
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": error_details,
            "message": exc.detail
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = {
        "error_type": "ValidationError",
        "error_message": "Request validation failed",
        "validation_errors": exc.errors(),
        "path": str(request.url),
        "method": request.method,
        "timestamp": datetime.now().isoformat()
    }
    
    # Log to console
    logger.warning(f"Validation Error: {error_details}")
    
    # Return error in API response
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": error_details,
            "message": "Request validation failed. Check the validation_errors field for details."
        }
    )

@app.exception_handler(ResponseValidationError)
async def response_validation_exception_handler(request: Request, exc: ResponseValidationError):
    error_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    error_details = {
        "error_id": error_id,
        "error_type": "ResponseValidationError",
        "error_message": "Response validation failed - likely a data type mismatch",
        "validation_errors": exc.errors(),
        "path": str(request.url),
        "method": request.method,
        "timestamp": datetime.now().isoformat()
    }
    
    # Log to console with full details
    logger.error(f"Response Validation Error {error_id}: {error_details}")
    logger.error(f"Full exception: {exc}")
    
    # Return error in API response
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": error_details,
            "message": "Internal server error: Response validation failed. This usually indicates a data type mismatch in the database or model."
        }
    )

# CORS middleware - Production + Development + Mobile
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.liftawaysolutions.com",
        "https://liftawaysolutions.com",
        "https://driver.liftawaysolutions.com",
        "https://admin.liftawaysolutions.com",
        "https://www.liftawayservices.com",
        "https://liftawayservices.com",
        "https://customer.liftawayservices.com",
        "https://admin.liftawayservices.com",
    ],
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?|capacitor://localhost|ionic://localhost|file://.*)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response logging middleware (simplified to avoid body consumption issues)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    
    # Log request (without body to avoid consumption issues)
    logger.info(f"📥 Request: {request.method} {request.url}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"📤 Response: {response.status_code} | Time: {process_time:.3f}s")
    
    return response

# Include driver/admin-related routers only
app.include_router(auth_api)  # Driver and Admin authentication API
app.include_router(driver_registration_router, prefix=f"{settings.API_V1_STR}")  # Driver registration with uploads
app.include_router(services, prefix=f"{settings.API_V1_STR}")
app.include_router(bookings, prefix=f"{settings.API_V1_STR}")
app.include_router(driver, prefix=f"{settings.API_V1_STR}")
app.include_router(admin, prefix=f"{settings.API_V1_STR}")
app.include_router(payments, prefix=f"{settings.API_V1_STR}")

app.include_router(stripe_payments.router, prefix=f"{settings.API_V1_STR}")
app.include_router(profile, prefix=f"{settings.API_V1_STR}")
app.include_router(issues_router, prefix=f"{settings.API_V1_STR}")
app.include_router(issues_driver_router, prefix=f"{settings.API_V1_STR}")
app.include_router(location_ws_router, prefix=f"{settings.API_V1_STR}")
app.include_router(driver_ratings_router, prefix=f"{settings.API_V1_STR}")
app.include_router(chat_router, prefix=f"{settings.API_V1_STR}")
app.include_router(notifications_router, prefix=f"{settings.API_V1_STR}")
app.include_router(driver_wallet_router, prefix=f"{settings.API_V1_STR}")
app.include_router(driver_stripe_setup_router, prefix=f"{settings.API_V1_STR}")
app.include_router(stripe_connect_webhook_router, prefix=f"{settings.API_V1_STR}")
app.include_router(platform_balance_router, prefix=f"{settings.API_V1_STR}")
# app.include_router(email_verification, prefix=f"{settings.API_V1_STR}")

@app.get("/")
async def root():
    return {
        "message": "Breakdown Assistance Driver/Admin API",
        "version": settings.VERSION,
        "docs": "/docs",
        "service_type": "Driver & Admin Service",
        "error_handling": "Enabled - errors will be shown in both console logs and API responses"
    }

@app.get("/technician/health")
def technician_health_check():
    return {"status": "Technician service running"}

@app.get("/technician/info")
def technician_info():
    return {
        "service": "Technician/Admin Service",
        "version": "1.0.0"
    }

@app.get("/health/")
async def health_check():
    health = {"status": "healthy", "service": "driver-admin"}
    
    # Check Redis connection
    try:
        client = redis_pool.get_client()
        await client.ping()
        await client.close()
        health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {str(e)}"
        health["status"] = "unhealthy"
    
    # Check Database connection
    try:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute("SELECT 1")
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["status"] = "unhealthy"
    
    return health


@app.get(f"{settings.API_V1_STR}/mapbox-token")
async def get_mapbox_token():
    """Return the public Mapbox token for client-side use (no authentication)."""
    token = getattr(settings, "MAPBOX_TOKEN", None)
    if not token:
        return {"mapbox_token": None}
    return {"mapbox_token": token}

@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    await manager.connect(websocket, role)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong to keep connection alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, role)

