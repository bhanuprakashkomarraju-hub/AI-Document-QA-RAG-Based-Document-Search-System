from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.services.metrics import QueryMetricsService

router = APIRouter(tags=["metrics"])


def get_metrics_service(request: Request) -> QueryMetricsService:
    return request.app.state.metrics_service


@router.get("/metrics")
async def get_metrics(metrics_service: QueryMetricsService = Depends(get_metrics_service)) -> dict:
    return metrics_service.snapshot()
