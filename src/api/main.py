import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
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


@app.get("/")
def root():
    from pathlib import Path
    
    static_file = Path(__file__).parent.parent / "static" / "index.html"
    if static_file.exists():
        return FileResponse(static_file)
    return {"message": "Orlando Park Assistant API"}
# Fixed root route - serve the static HTML file directly
import os as _os
_html_path = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'index.html')

@app.get("/setup")  
def setup_page():
    if _os.path.exists(_html_path):
        with open(_html_path) as f:
            content = f.read()
        from fastapi import Response
        return Response(content=content, media_type="text/html")
    return {"error": "setup page not found"}


@app.get("/queues/live")
def live_queues():
    """Busca filas ao vivo da ThemeParks.wiki (para debug e monitoramento)."""
    from src.services.queue_fetcher import fetch_live_queues
    queues = fetch_live_queues()
    if queues is None:
        return {"status": "unavailable", "queues": {}}
    operating = {k: v for k, v in queues.items() if v < 999}
    closed = [k for k, v in queues.items() if v == 999]
    return {
        "status": "ok",
        "operating": operating,
        "closed": closed,
        "total": len(queues),
    }


# ── Admin endpoints ──────────────────────────────────────────────

import os as _os
_admin_path = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'admin.html')
_parks_seed_path = _os.path.join(_os.path.dirname(__file__), '..', '..', 'data', 'seeds', 'all_parks_attractions.json')



@app.post("/admin/login")
async def admin_login(request: Request):
    import os
    body = await request.json()
    email = body.get("email", "")
    password = body.get("password", "")
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@vturismo.com.br")
    admin_pass  = os.environ.get("ADMIN_PASS", "VTurismo@2025")
    if email == admin_email and password == admin_pass:
        return {"ok": True}
    return {"ok": False}

@app.get("/admin")
def admin_page():
    from fastapi import Response
    if _os.path.exists(_admin_path):
        with open(_admin_path, encoding='utf-8') as f:
            content = f.read()
        return Response(content=content, media_type="text/html")
    return {"error": "admin page not found"}


@app.get("/admin/groups")
def admin_groups():
    import json
    from src.infra.database.connection import get_connection
    try:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT g.group_id, g.whatsapp_number, g.park_id, g.visit_date,
                       g.profile_id, g.setup_complete, g.created_at,
                       COALESCE(g.status, 'active') as status,
                       COUNT(m.member_id) as member_count,
                       p.must_do_attractions
                FROM groups g
                LEFT JOIN members m ON m.group_id = g.group_id
                LEFT JOIN group_preferences p ON p.group_id = g.group_id
                GROUP BY g.group_id
                ORDER BY g.whatsapp_number, g.created_at DESC
            """).fetchall()
            groups = []
            for r in rows:
                d = dict(r)
                try:
                    d['must_do'] = json.loads(d.get('must_do_attractions') or '[]')
                except:
                    d['must_do'] = []
                groups.append(d)
            return {"groups": groups, "total": len(groups)}
    except Exception as e:
        return {"groups": [], "total": 0, "error": str(e)}


@app.get("/admin/attractions")
def admin_attractions():
    import json
    result = {}

    # Load all_parks_attractions.json (8 parques)
    if _os.path.exists(_parks_seed_path):
        with open(_parks_seed_path, encoding='utf-8') as f:
            result = json.load(f)

    # Load magic_kingdom_attractions.json e converte para o mesmo formato
    mk_path = _os.path.join(_os.path.dirname(__file__), '..', '..', 'data', 'seeds', 'magic_kingdom_attractions.json')
    if _os.path.exists(mk_path):
        with open(mk_path, encoding='utf-8') as f:
            mk_raw = json.load(f)
        mk_attractions = mk_raw.get('mk_attractions', {})
        # Converte formato antigo para o novo
        converted = {}
        for slug, a in mk_attractions.items():
            converted[slug] = {
                'name': a.get('name', slug),
                'area': a.get('area', ''),
                'type': a.get('type', ''),
                'intensity': a.get('intensity', 'moderate'),
                'min_height_cm': a.get('min_height_cm', 0),
                'indoor': a.get('indoor', False),
                'active': a.get('active', True),
                'status': 'open' if a.get('active', True) else 'closed',
                'tags': a.get('tags', []),
                'description_pt': a.get('description_pt', a.get('strategic_notes', '')),
                'video_url': a.get('video_url', ''),
            }
        result['magic_kingdom'] = {
            'park_name': 'Magic Kingdom',
            'park_id': 'magic_kingdom',
            'entity_id': '75ea578a-adc8-4116-a54d-dccb60765ef9',
            'attractions': converted,
        }

    return result


@app.patch("/admin/attractions/{park_id}/{attr_slug}")
async def admin_update_attraction(park_id: str, attr_slug: str, request: "Request"):
    import json
    from fastapi import Request
    body = await request.json()
    if not _os.path.exists(_parks_seed_path):
        return {"error": "seed not found"}
    with open(_parks_seed_path, encoding='utf-8') as f:
        data = json.load(f)
    park = data.get(park_id, {})
    attrs = park.get('attractions', {})
    if attr_slug not in attrs:
        return {"error": "attraction not found"}
    if 'description_pt' in body:
        attrs[attr_slug]['description_pt'] = body['description_pt']
    if 'video_url' in body:
        attrs[attr_slug]['video_url'] = body['video_url']
    if 'status' in body and body['status']:
        status = body['status']
        attrs[attr_slug]['status'] = status
        attrs[attr_slug]['active'] = (status == 'open')
    with open(_parks_seed_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": True, "updated": attr_slug}
