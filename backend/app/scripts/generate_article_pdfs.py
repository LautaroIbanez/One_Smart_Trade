"""Generate PDF files from knowledge base articles."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.core.config import settings
from app.db.models import KnowledgeArticleORM
from app.core.logging import logger

try:
    import markdown
    from weasyprint import HTML
except ImportError:
    logger.error("Required packages not installed. Install with: poetry add markdown weasyprint")
    sys.exit(1)


def generate_pdf_from_markdown(content: str, title: str, output_path: Path) -> None:
    """Generate PDF from markdown content."""
    # Convert markdown to HTML
    try:
        html_content = markdown.markdown(content, extensions=['extra', 'codehilite'])
    except Exception:
        # Fallback to basic markdown if extensions fail
        html_content = markdown.markdown(content)
    
    # Create full HTML document with styling
    html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: 'DejaVu Sans', Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #333;
            }}
            h1 {{
                font-size: 24pt;
                color: #2c3e50;
                margin-top: 0;
                margin-bottom: 20pt;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10pt;
            }}
            h2 {{
                font-size: 18pt;
                color: #34495e;
                margin-top: 20pt;
                margin-bottom: 12pt;
            }}
            h3 {{
                font-size: 14pt;
                color: #555;
                margin-top: 16pt;
                margin-bottom: 8pt;
            }}
            p {{
                margin-bottom: 10pt;
                text-align: justify;
            }}
            ul, ol {{
                margin-bottom: 10pt;
                padding-left: 20pt;
            }}
            li {{
                margin-bottom: 5pt;
            }}
            strong {{
                color: #2c3e50;
                font-weight: bold;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2pt 4pt;
                border-radius: 3pt;
                font-family: 'Courier New', monospace;
                font-size: 10pt;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 10pt;
                border-radius: 5pt;
                overflow-x: auto;
                margin-bottom: 10pt;
            }}
            blockquote {{
                border-left: 4px solid #3498db;
                padding-left: 15pt;
                margin-left: 0;
                color: #555;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # Generate PDF
    HTML(string=html_doc).write_pdf(output_path)
    logger.info(f"Generated PDF: {output_path}")


def generate_all_article_pdfs() -> None:
    """Generate PDFs for all articles in the knowledge base."""
    # Create education directory
    education_dir = Path(settings.DATA_DIR) / "education"
    education_dir.mkdir(parents=True, exist_ok=True)
    
    db = SessionLocal()
    try:
        articles = db.query(KnowledgeArticleORM).filter(KnowledgeArticleORM.is_active == True).all()
        logger.info(f"Found {len(articles)} active articles")
        
        for article in articles:
            try:
                # Generate PDF filename
                pdf_filename = f"{article.slug}.pdf"
                pdf_path = education_dir / pdf_filename
                
                # Generate PDF
                generate_pdf_from_markdown(article.content, article.title, pdf_path)
                
                # Update article with pdf_path (relative to DATA_DIR)
                article.pdf_path = f"education/{pdf_filename}"
                if not article.download_url:
                    article.download_url = f"/api/v1/knowledge/articles/{article.slug}/pdf"
                
                logger.info(f"Updated article '{article.title}' with pdf_path: {article.pdf_path}")
            except Exception as e:
                logger.error(f"Error generating PDF for article '{article.title}': {e}", exc_info=True)
        
        db.commit()
        logger.info(f"Successfully generated PDFs for {len(articles)} articles")
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating PDFs: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    generate_all_article_pdfs()

