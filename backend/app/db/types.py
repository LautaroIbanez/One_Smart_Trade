"""SQLite-safe UUID type for cross-dialect compatibility."""
from __future__ import annotations

from uuid import UUID
from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from app.core.config import settings


class SqliteUUID(TypeDecorator):
    """
    UUID type that works on both PostgreSQL and SQLite.
    
    On PostgreSQL: uses native UUID type with as_uuid=True
    On SQLite: stores as CHAR(36) string and converts to/from UUID objects
    """
    
    impl = String
    cache_ok = True
    
    def __init__(self, as_uuid: bool = True):
        """Initialize with as_uuid flag (default True for UUID objects)."""
        self.as_uuid = as_uuid
        super().__init__(length=36)
    
    def load_dialect_impl(self, dialect):
        """Return the appropriate type based on dialect."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresUUID(as_uuid=self.as_uuid))
        else:
            return dialect.type_descriptor(String(36))
    
    def process_bind_param(self, value, dialect):
        """Convert Python value to database value."""
        if value is None:
            return None
        
        if dialect.name == "postgresql":
            # PostgreSQL handles UUID natively
            if isinstance(value, str):
                return UUID(value)
            return value
        else:
            # SQLite: always store as string
            if isinstance(value, UUID):
                return str(value)
            if isinstance(value, str):
                # Validate it's a valid UUID string
                try:
                    UUID(value)
                    return value
                except (ValueError, AttributeError):
                    # Legacy integer IDs: convert to default user ID
                    from app.core.config import settings
                    return settings.DEFAULT_USER_ID
            # Handle legacy integer IDs
            if isinstance(value, int):
                from app.core.config import settings
                return settings.DEFAULT_USER_ID
            return str(value)
    
    def process_result_value(self, value, dialect):
        """Convert database value to Python value."""
        if value is None:
            return None
        
        if dialect.name == "postgresql":
            # PostgreSQL returns UUID objects when as_uuid=True
            return value
        else:
            # SQLite: convert string to UUID if as_uuid=True, else return string
            if self.as_uuid:
                try:
                    if isinstance(value, str):
                        return UUID(value)
                    if isinstance(value, int):
                        # Legacy integer ID: return default user UUID
                        from app.core.config import settings
                        return UUID(settings.DEFAULT_USER_ID)
                    return UUID(str(value))
                except (ValueError, AttributeError, TypeError):
                    # Invalid UUID format: return default
                    from app.core.config import settings
                    return UUID(settings.DEFAULT_USER_ID)
            else:
                return str(value) if value is not None else None

