from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.services.ingestion import IngestionService

router = APIRouter(tags=["upload"])


def get_ingestion_service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> dict:
    # Healthcare pipeline accepts structured/unstructured PDF records.
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required.")
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are accepted.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        result = ingestion_service.ingest_pdf(payload, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ingestion failed.") from exc

    return {
        "status": "success",
        "filename": result.filename,
        "chunks_created": result.chunks_created,
        "characters_processed": result.characters_processed,
    }
