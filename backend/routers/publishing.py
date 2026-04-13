from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from backend.services.publishing_service import build_robots_txt, build_rss_xml, build_sitemap_xml

router = APIRouter(tags=["publishing"])


@router.get("/sitemap.xml")
def sitemap():
    return Response(content=build_sitemap_xml(), media_type="application/xml")


@router.get("/rss.xml")
def rss():
    return Response(content=build_rss_xml(), media_type="application/rss+xml")


@router.get("/robots.txt")
def robots():
    return PlainTextResponse(build_robots_txt(), media_type="text/plain; charset=utf-8")
