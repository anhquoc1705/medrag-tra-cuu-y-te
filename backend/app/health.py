"""API /health: kiểm tra backend kết nối được với Elasticsearch, Milvus và PostgreSQL."""

import time

import psycopg
from elasticsearch import Elasticsearch
from fastapi import APIRouter, Response, status
from pymilvus import MilvusClient

from app.config import get_settings

router = APIRouter(tags=["health"])


def _check(fn) -> dict:
    """Chạy một hàm kiểm tra, trả về trạng thái + thời gian phản hồi; không để lỗi làm sập API."""
    start = time.perf_counter()
    try:
        detail = fn()
        return {"ok": True, "ms": round((time.perf_counter() - start) * 1000), **detail}
    except Exception as e:  # noqa: BLE001 – mọi lỗi kết nối đều báo về dạng ok=False
        return {"ok": False, "ms": round((time.perf_counter() - start) * 1000), "error": f"{type(e).__name__}: {e}"}


def check_elasticsearch() -> dict:
    s = get_settings()
    es = Elasticsearch(s.es_url, request_timeout=s.health_timeout)
    try:
        info = es.info()
        cluster = es.cluster.health()
        return {"version": info["version"]["number"], "cluster_status": cluster["status"]}
    finally:
        es.close()


def check_milvus() -> dict:
    s = get_settings()
    client = MilvusClient(uri=s.milvus_uri, timeout=s.health_timeout)
    try:
        return {"version": client.get_server_version(), "collections": client.list_collections()}
    finally:
        client.close()


def check_postgres() -> dict:
    s = get_settings()
    with psycopg.connect(s.database_url, connect_timeout=int(s.health_timeout)) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
    return {"version": version}


@router.get("/health")
def health(response: Response) -> dict:
    services = {
        "elasticsearch": _check(check_elasticsearch),
        "milvus": _check(check_milvus),
        "postgres": _check(check_postgres),
    }
    all_ok = all(svc["ok"] for svc in services.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if all_ok else "degraded", "services": services}
