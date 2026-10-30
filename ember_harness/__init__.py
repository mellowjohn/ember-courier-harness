"""Local contract schema and approval gate. No tool execution or network calls."""
from .core import Harness, canonical, content_hash, draft, validate

__all__ = ["Harness", "canonical", "content_hash", "draft", "validate"]
