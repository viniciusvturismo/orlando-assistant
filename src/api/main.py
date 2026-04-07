import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.groups import router as groups_router
from .routers.recommendations import context_router, rec_router
from .middleware.error_handler import domain_exception_handler, unhandled_exception_handler
from ..domain.exceptions.domain_exceptions import OrlandoBaseException
from ..infra.database.connection import init_db
from ..infra.repositories.attractions_repository import get_attractions_repository
from ..config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting orlando-assistant (env=%s)", settings.env)
    init_db()
    repo = get_attractions_repository()
    logger.info("Loaded %d attractions", len(repo.get_all_active()))
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Orlando Park Assistant",
    version="0.1.0",
    description="MVP — assistente de decisão para famílias brasileiras no Magic Kingdom",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(OrlandoBaseException, domain_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(groups_router)
app.include_router(context_router)
app.include_router(rec_router)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.env}


@app.get("/setup")
def setup_page():
    import os
    from fastapi import Response
    html_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'index.html')
    if os.path.exists(html_path):
        with open(html_path) as f:
            content = f.read()
        return Response(content=content, media_type="text/html")
    return {"error": "page not found"}
