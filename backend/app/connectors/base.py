"""
Base connector interface.

All data source connectors implement this interface, making the ingestion
pipeline data-source-agnostic. Swapping or adding a connector requires no
changes to the chunking, embedding, retrieval, or workflow layers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ConnectorResult:
    """Standardised output produced by every connector."""
    content: str                      # Full plain-text content (PII-redacted)
    title: str
    source_type: str                  # edgar, pdf, web, text, sharepoint, dataverse, …
    source_url: Optional[str]
    sha256: str                       # For deduplication
    metadata: Dict[str, Any]          # Source-specific metadata (company, filing_type, …)
    sections: List[Dict[str, Any]]    # Structured sections for better chunking


class BaseConnector(ABC):
    """
    Abstract base for all data source connectors.

    Implementing a new connector:
        1. Subclass BaseConnector
        2. Implement fetch() — return a ConnectorResult
        3. Register in connectors/__init__.py
        4. Add the source_type to the documents router

    No other layers need to change.
    """

    #: Unique identifier for this connector, used as Document.source_type
    source_type: str = ""

    @abstractmethod
    async def fetch(self, **kwargs) -> ConnectorResult:
        """
        Fetch and parse content from the data source.

        Returns a ConnectorResult ready for chunking and embedding.
        All PII redaction should happen inside this method.
        """

    @property
    def display_name(self) -> str:
        return self.source_type.replace("_", " ").title()
