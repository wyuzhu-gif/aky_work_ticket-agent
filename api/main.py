import sys
from pathlib import Path

# Ensure project root is on sys.path so `common` can be imported when running from app/api
API_DIR = Path(__file__).resolve().parent
APP_DIR = API_DIR.parent
ROOT_DIR = APP_DIR.parent  # project root containing `common`
# Put project roots at the front of sys.path to avoid shadowing by similarly named packages.
for p in (ROOT_DIR, APP_DIR):
    p_str = str(p)
    if p_str in sys.path:
        sys.path.remove(p_str)
    sys.path.insert(0, p_str)

from common.logger import get_logger
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from middleware.logging import LoggingMiddleware, setup_logging
from config.config import settings
from routers import issues
from routers import review_external, files, rules, rule_documents, permits, chat
from routers import sqlagent_admin
from routers import dashboard, wiki_router

# Set up logging configuration
setup_logging()

logging = get_logger(__name__)

# SmartQuery 初始化（在 lifespan 中调用）
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化 SmartQuery"""
    try:
        from smart_query.service import initialize_smartquery
        initialize_smartquery(settings)
        logging.info("SmartQuery NL2SQL system initialized via lifespan")
    except Exception as e:
        logging.error(f"SmartQuery initialization failed: {e}")
        logging.warning("SmartQuery features will be unavailable")
    yield
    logging.info("Application shutdown")

# Initialize FastAPI app
app = FastAPI(
    swagger_ui_oauth2_redirect_url="/oauth2-redirect",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True,
        "clientId": settings.aad_client_id or None,
    },
    lifespan=lifespan,
)

# Add middlewares
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(issues.router)
app.include_router(review_external.router)
app.include_router(files.router)
app.include_router(rules.router)
app.include_router(rule_documents.router)
app.include_router(permits.router)
app.include_router(chat.router)
app.include_router(sqlagent_admin.router)
app.include_router(dashboard.router)
app.include_router(wiki_router.router)


# Health check endpoint
@app.get(
    "/api/health",
    summary="Health Check",
    response_description="Health status of the API",
)
def health_check():
    logging.info("Health check endpoint called.")
    return Response(status_code=204)


# Mount the UI at the root path (should come last so it doesn't interfere with /api routes)
if settings.serve_static:
    static_dir = Path("www")
    if static_dir.exists():
        # React SPA 用 history API 路由, 但浏览器直接访问 /smart-query 这种非根路径
        # 时, 后端需要 fallback 返回 index.html 让 React 接管
        # mount 前先添加 SPA fallback - 所有非 api/static 的 GET 请求都返回 index.html
        from fastapi.responses import FileResponse

        # 列出所有 React 路由 (frontend/src/router.tsx 里定义)
        async def spa_fallback_handler():
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            from fastapi import HTTPException
            raise HTTPException(status_code=404)

        for route in ["/smart-query", "/ticket-review", "/ticket-review-v2", "/agent-admin", "/dashboard", "/settings"]:
            app.get(route, include_in_schema=False)(spa_fallback_handler)

        app.mount("/", StaticFiles(directory=static_dir, html=True))
    else:
        logging.warning("Static directory 'www' not found. Set SERVE_STATIC=False or build UI into app/api/www.")


# Exception handler only for HTTPExceptions
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logging.error(f"HTTPException occurred: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTPException", "message": exc.detail},
    )


# Exception handler for general exceptions
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unexpected error occurred: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "500 Internal Server Error",
            "message": str(exc),
        },
    )
