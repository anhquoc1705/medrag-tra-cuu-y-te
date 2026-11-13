"""API POST /search: thử tìm kiếm BM25 / vector / hybrid (dùng cho giao diện quản trị và đánh giá)."""

import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.search import SearchFilters, search

router = APIRouter(tags=["search"])


class FiltersIn(BaseModel):
    topic: list[str] = []
    jurisdiction: list[str] = []
    language: list[str] = []
    target_population: list[str] = []
    document_id: list[str] = []


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["bm25", "vector", "hybrid"] = "hybrid"
    top_k: int | None = Field(default=None, ge=1, le=20)
    filters: FiltersIn = FiltersIn()


@router.post("/search")
def search_endpoint(req: SearchRequest) -> dict:
    started = time.perf_counter()
    try:
        results = search(req.query, req.mode, req.top_k, SearchFilters(**req.filters.model_dump()))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "query": req.query,
        "mode": req.mode,
        "took_ms": round((time.perf_counter() - started) * 1000),
        "results": results,
    }
