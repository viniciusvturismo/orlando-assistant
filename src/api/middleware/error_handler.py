import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from ...domain.exceptions.domain_exceptions import OrlandoBaseException

logger = logging.getLogger(__name__)


async def domain_exception_handler(request: Request, exc: OrlandoBaseException) -> JSONResponse:
    path = getattr(getattr(request, 'url', None), 'path', '?')
    logger.warning("Domain exception on %s: %s", path, exc)
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    path = getattr(getattr(request, 'url', None), 'path', '?')
    logger.error("Unhandled exception on %s: %s", path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
