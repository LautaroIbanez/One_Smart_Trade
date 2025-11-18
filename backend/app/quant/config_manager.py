"""Signal configuration manager with versioning and digest calculation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from app.core.logging import logger


class SignalConfigManager:
    """
    Manages signal configuration with versioning and digest calculation.
    
    This class ensures that all signal parameters (weights, thresholds, biases)
    are loaded from versioned configuration files and tracked via digests
    for full traceability.
    
    Usage:
        config = SignalConfigManager()
        params = config.get_params()
        digest = config.get_digest()
        version = config.get_version()
    """
    
    def __init__(self, config_path: Path | None = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to params.yaml file. If None, uses default location.
        """
        if config_path is None:
            # Default to params.yaml in the same directory as this file
            config_path = Path(__file__).parent / "params.yaml"
        
        self.config_path = Path(config_path)
        self._params: dict[str, Any] | None = None
        self._digest: str | None = None
        self._version: str | None = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}, using empty config")
            self._params = {}
            self._digest = self._calculate_digest({})
            self._version = "unknown"
            return
        
        try:
            with self.config_path.open(encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            
            if not isinstance(loaded, dict):
                logger.error(f"Invalid config format in {self.config_path}, expected dict")
                loaded = {}
            
            self._params = loaded
            
            # Extract version if present, otherwise use digest
            self._version = loaded.get("version") or loaded.get("config_version")
            if not self._version:
                # Use short hash as version identifier
                self._digest = self._calculate_digest(loaded)
                self._version = f"hash:{self._digest[:12]}"
            else:
                # Still calculate digest for tracking
                self._digest = self._calculate_digest(loaded)
            
            logger.debug(f"Loaded signal config from {self.config_path}, version: {self._version}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML config {self.config_path}: {e}")
            self._params = {}
            self._digest = self._calculate_digest({})
            self._version = "error"
        except Exception as e:
            logger.error(f"Error loading config from {self.config_path}: {e}")
            self._params = {}
            self._digest = self._calculate_digest({})
            self._version = "error"
    
    def _calculate_digest(self, params: dict[str, Any]) -> str:
        """
        Calculate SHA-256 digest of configuration.
        
        Uses deterministic JSON serialization to ensure same config produces same hash.
        
        Args:
            params: Configuration dictionary
            
        Returns:
            SHA-256 hex digest (64 characters)
        """
        # Normalize by sorting keys and using consistent formatting
        normalized = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    def get_params(self) -> dict[str, Any]:
        """
        Get current configuration parameters.
        
        Returns:
            Dictionary with all signal parameters
        """
        if self._params is None:
            self._load_config()
        return self._params.copy() if self._params else {}
    
    def get_digest(self) -> str:
        """
        Get SHA-256 digest of current configuration.
        
        This digest uniquely identifies the configuration and should be stored
        with each recommendation for traceability.
        
        Returns:
            SHA-256 hex digest string
        """
        if self._digest is None:
            params = self.get_params()
            self._digest = self._calculate_digest(params)
        return self._digest
    
    def get_version(self) -> str:
        """
        Get human-readable version identifier.
        
        Returns version from config file if present, otherwise returns
        a short hash-based identifier.
        
        Returns:
            Version string (e.g., "1.0.0" or "hash:abc123def456")
        """
        if self._version is None:
            self._load_config()
        return self._version or "unknown"
    
    def get_file_content_hash(self) -> str:
        """
        Calculate hash of the raw config file content.
        
        This is useful for detecting file changes even if the parsed
        content is the same (e.g., whitespace changes).
        
        Returns:
            SHA-256 hex digest of file content
        """
        if not self.config_path.exists():
            return "unknown"
        
        try:
            with self.config_path.open("rb") as fh:
                content = fh.read()
            return hashlib.sha256(content).hexdigest()
        except Exception as e:
            logger.error(f"Error calculating file hash for {self.config_path}: {e}")
            return "error"
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._params = None
        self._digest = None
        self._version = None
        self._load_config()
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration structure.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: list[str] = []
        params = self.get_params()
        
        # Check required top-level keys
        required_sections = ["momentum", "mean_reversion", "breakout", "volatility", "aggregate"]
        for section in required_sections:
            if section not in params:
                errors.append(f"Missing required section: {section}")
        
        # Validate aggregate section structure
        if "aggregate" in params:
            aggregate = params["aggregate"]
            if not isinstance(aggregate, dict):
                errors.append("aggregate section must be a dictionary")
            else:
                # Check for required thresholds
                if "buy_threshold" not in aggregate:
                    errors.append("aggregate.buy_threshold is required")
                if "sell_threshold" not in aggregate:
                    errors.append("aggregate.sell_threshold is required")
                
                # Validate vector_bias if present
                if "vector_bias" in aggregate:
                    if not isinstance(aggregate["vector_bias"], dict):
                        errors.append("aggregate.vector_bias must be a dictionary")
        
        return len(errors) == 0, errors


# Global instance for convenience
_default_config_manager: SignalConfigManager | None = None


def get_signal_config_manager(config_path: Path | None = None) -> SignalConfigManager:
    """
    Get or create the default SignalConfigManager instance.
    
    Args:
        config_path: Optional path to config file. Only used on first call.
    
    Returns:
        SignalConfigManager instance
    """
    global _default_config_manager
    if _default_config_manager is None:
        _default_config_manager = SignalConfigManager(config_path)
    return _default_config_manager


def get_signal_params() -> dict[str, Any]:
    """Get current signal parameters from default config manager."""
    return get_signal_config_manager().get_params()


def get_signal_config_digest() -> str:
    """Get digest of current signal configuration."""
    return get_signal_config_manager().get_digest()


def get_signal_config_version() -> str:
    """Get version of current signal configuration."""
    return get_signal_config_manager().get_version()

