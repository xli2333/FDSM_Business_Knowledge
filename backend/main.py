from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import ALLOWED_ORIGINS, APP_TITLE, EDITORIAL_UPLOADS_DIR, MEDIA_UPLOADS_DIR
from backend.database import ensure_database_ready
from backend.routers.analytics import router as analytics_router
from backend.routers.admin import router as admin_router
from backend.routers.auth import router as auth_router
from backend.routers.articles import router as articles_router
from backend.routers.billing import router as billing_router
from backend.routers.chat import router as chat_router
from backend.routers.columns import router as columns_router
from backend.routers.commerce import router as commerce_router
from backend.routers.editorial import router as editorial_router
from backend.routers.follows import router as follows_router
from backend.routers.home import router as home_router
from backend.routers.media import router as media_router
from backend.routers.me import router as me_router
from backend.routers.membership import router as membership_router
from backend.routers.organizations import router as organizations_router
from backend.routers.publishing import router as publishing_router
from backend.routers.search import router as search_router
from backend.routers.tags import router as tags_router
from backend.routers.time_machine import router as time_machine_router
from backend.routers.topics import router as topics_router
from backend.routers.user_knowledge import router as user_knowledge_router

from backend.database import ensure_runtime_tables
from backend.services.media_service import sync_local_audio_library

ensure_database_ready()
ensure_runtime_tables()
EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
sync_local_audio_library()

app = FastAPI(title=APP_TITLE)
audio_directory = Path(__file__).resolve().parent.parent / "audio"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/audio-files", StaticFiles(directory=audio_directory, check_dir=False), name="audio-files")
app.mount("/editorial-uploads", StaticFiles(directory=EDITORIAL_UPLOADS_DIR, check_dir=False), name="editorial-uploads")
app.mount("/media-uploads", StaticFiles(directory=MEDIA_UPLOADS_DIR, check_dir=False), name="media-uploads")

app.include_router(home_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(membership_router)
app.include_router(follows_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(me_router)
app.include_router(user_knowledge_router)
app.include_router(media_router)
app.include_router(organizations_router)
app.include_router(search_router)
app.include_router(articles_router)
app.include_router(tags_router)
app.include_router(columns_router)
app.include_router(topics_router)
app.include_router(chat_router)
app.include_router(time_machine_router)
app.include_router(commerce_router)
app.include_router(editorial_router)
app.include_router(publishing_router)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": APP_TITLE,
        "scope": "business-only",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
