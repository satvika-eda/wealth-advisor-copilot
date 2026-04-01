"""Auth and access-control constants shared across the application."""
from typing import Dict, FrozenSet

# Used in: document creation/listing, RAG retrieval, and workflow policy check.
ROLE_SENSITIVITY_ACCESS: Dict[str, FrozenSet[str]] = {
    "advisor":    frozenset({"public", "internal"}),
    "admin":      frozenset({"public", "internal", "confidential"}),
    "compliance": frozenset({"public", "internal", "confidential", "restricted"}),
}
