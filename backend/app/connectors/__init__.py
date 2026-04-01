"""
Pluggable data source connectors.

Architecture intent:
  Each connector is an independent, interchangeable implementation of BaseConnector.
  The ingestion layer (documents router) calls connectors by source type — new data
  sources are added by implementing BaseConnector without touching orchestration or
  retrieval logic.

  Current connectors:
    - EdgarConnector   — SEC EDGAR filings (10-K, 10-Q, 8-K)
    - PdfConnector     — PDF file uploads
    - WebConnector     — Web URL fetch + extraction
    - TextConnector    — Plain text / manual entry

  Stub connectors (interface-compatible, ready for implementation):
    - SharePointConnector  — Microsoft SharePoint / OneDrive document libraries
    - DataverseConnector   — Microsoft Dataverse structured records
    - ConfluenceConnector  — Confluence knowledge bases
    - DatabaseConnector    — Internal relational database tables

  Integration note:
    This design allows the retrieval and workflow layers to remain unchanged
    when new institutional data sources are onboarded. Each connector produces
    a ParsedDocument, which feeds the same chunking → embedding → retrieval pipeline.
"""

from app.connectors.base import BaseConnector, ConnectorResult
from app.connectors.edgar import EdgarConnector
from app.connectors.pdf import PdfConnector
from app.connectors.web import WebConnector
from app.connectors.text import TextConnector
from app.connectors.enterprise_stubs import SharePointConnector, DataverseConnector

__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "EdgarConnector",
    "PdfConnector",
    "WebConnector",
    "TextConnector",
    "SharePointConnector",
    "DataverseConnector",
]
