"""Knowledge base endpoints."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.db.crud import (
    get_article_by_slug,
    get_articles_by_category,
    get_contextual_articles,
    get_user_reading_history,
    record_user_reading,
)

router = APIRouter()


@router.get("/articles/contextual")
async def get_contextual_articles_endpoint(
    user_id: str = Query(..., description="User UUID"),
    trigger_type: str | None = Query(None, description="Trigger type: cooldown|leverage|drawdown|overtrading"),
    category: str | None = Query(None, description="Category filter: emotional_management|risk_limits|rest|journaling"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of articles to return"),
) -> dict[str, Any]:
    """
    Get contextual articles based on trigger conditions.
    
    Returns articles relevant to the current user state (e.g., after cooldown activation).
    """
    try:
        with SessionLocal() as db:
            articles = get_contextual_articles(
                db,
                user_id,
                trigger_type=trigger_type,
                category=category,
                limit=limit,
            )
            
            return {
                "status": "ok",
                "user_id": user_id,
                "trigger_type": trigger_type,
                "articles": [
                    {
                        "id": article.id,
                        "title": article.title,
                        "slug": article.slug,
                        "category": article.category,
                        "summary": article.summary,
                        "tags": article.tags or [],
                        "priority": article.priority,
                        "has_pdf": article.pdf_path is not None,
                        "created_at": article.created_at.isoformat() if article.created_at else None,
                    }
                    for article in articles
                ],
                "count": len(articles),
            }
    except Exception as e:
        logger.error(f"Error fetching contextual articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles/{slug}")
async def get_article_by_slug_endpoint(
    slug: str,
    user_id: str = Query(..., description="User UUID"),
    mark_as_read: bool = Query(True, description="Mark article as read for user"),
) -> dict[str, Any]:
    """
    Get full article content by slug.
    
    Optionally marks the article as read for the user.
    """
    try:
        with SessionLocal() as db:
            article = get_article_by_slug(db, slug)
            
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            # Record reading if requested
            if mark_as_read:
                try:
                    record_user_reading(db, user_id, article.id, pdf_downloaded=False)
                except Exception as e:
                    logger.warning(f"Failed to record reading: {e}", exc_info=True)
            
            return {
                "status": "ok",
                "article": {
                    "id": article.id,
                    "title": article.title,
                    "slug": article.slug,
                    "category": article.category,
                    "content": article.content,
                    "summary": article.summary,
                    "tags": article.tags or [],
                    "priority": article.priority,
                    "has_pdf": article.pdf_path is not None,
                    "pdf_path": article.pdf_path,
                    "created_at": article.created_at.isoformat() if article.created_at else None,
                    "updated_at": article.updated_at.isoformat() if article.updated_at else None,
                },
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching article: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles/category/{category}")
async def get_articles_by_category_endpoint(
    category: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of articles to return"),
) -> dict[str, Any]:
    """
    Get all articles in a category.
    
    Categories: emotional_management, risk_limits, rest, journaling
    """
    try:
        with SessionLocal() as db:
            articles = get_articles_by_category(db, category, limit=limit)
            
            return {
                "status": "ok",
                "category": category,
                "articles": [
                    {
                        "id": article.id,
                        "title": article.title,
                        "slug": article.slug,
                        "summary": article.summary,
                        "tags": article.tags or [],
                        "priority": article.priority,
                        "has_pdf": article.pdf_path is not None,
                        "created_at": article.created_at.isoformat() if article.created_at else None,
                    }
                    for article in articles
                ],
                "count": len(articles),
            }
    except Exception as e:
        logger.error(f"Error fetching articles by category: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles/{slug}/pdf")
async def download_article_pdf(
    slug: str,
    user_id: str = Query(..., description="User UUID"),
) -> StreamingResponse | dict[str, Any]:
    """
    Download article as PDF.
    
    Records PDF download in user reading history.
    """
    try:
        with SessionLocal() as db:
            article = get_article_by_slug(db, slug)
            
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            if not article.pdf_path:
                raise HTTPException(status_code=404, detail="PDF not available for this article")
            
            # Record PDF download
            try:
                record_user_reading(db, user_id, article.id, pdf_downloaded=True)
            except Exception as e:
                logger.warning(f"Failed to record PDF download: {e}", exc_info=True)
            
            # Get PDF file path
            pdf_path = Path(settings.DATA_DIR) / article.pdf_path
            if not pdf_path.exists():
                logger.error(f"PDF file not found: {pdf_path}")
                raise HTTPException(status_code=404, detail="PDF file not found on server")
            
            return FileResponse(
                path=str(pdf_path),
                filename=f"{article.slug}.pdf",
                media_type="application/pdf",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/readings/history")
async def get_user_reading_history_endpoint(
    user_id: str = Query(..., description="User UUID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of readings to return"),
) -> dict[str, Any]:
    """
    Get user's reading history.
    
    Returns articles the user has read, with last read date and read count.
    """
    try:
        with SessionLocal() as db:
            readings = get_user_reading_history(db, user_id, limit=limit)
            
            return {
                "status": "ok",
                "user_id": user_id,
                "readings": [
                    {
                        "id": reading.id,
                        "article_id": reading.article_id,
                        "first_read_at": reading.first_read_at.isoformat() if reading.first_read_at else None,
                        "last_read_at": reading.last_read_at.isoformat() if reading.last_read_at else None,
                        "read_count": reading.read_count,
                        "pdf_downloaded": reading.pdf_downloaded,
                        "pdf_downloaded_at": reading.pdf_downloaded_at.isoformat() if reading.pdf_downloaded_at else None,
                    }
                    for reading in readings
                ],
                "count": len(readings),
            }
    except Exception as e:
        logger.error(f"Error fetching reading history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/articles/{slug}/read")
async def mark_article_as_read_endpoint(
    slug: str,
    user_id: str = Query(..., description="User UUID"),
) -> dict[str, Any]:
    """
    Mark an article as read for the user.
    
    Creates or updates user reading record.
    """
    try:
        with SessionLocal() as db:
            article = get_article_by_slug(db, slug)
            
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            reading = record_user_reading(db, user_id, article.id, pdf_downloaded=False)
            
            return {
                "status": "ok",
                "user_id": user_id,
                "article_id": article.id,
                "reading": {
                    "id": reading.id,
                    "first_read_at": reading.first_read_at.isoformat() if reading.first_read_at else None,
                    "last_read_at": reading.last_read_at.isoformat() if reading.last_read_at else None,
                    "read_count": reading.read_count,
                    "pdf_downloaded": reading.pdf_downloaded,
                },
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking article as read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




