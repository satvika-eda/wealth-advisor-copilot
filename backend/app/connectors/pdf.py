"""PDF file connector."""
from app.connectors.base import BaseConnector, ConnectorResult
from app.rag.parser import DocumentParser


class PdfConnector(BaseConnector):
    source_type = "pdf"

    def __init__(self):
        self._parser = DocumentParser(redact_pii=True)

    async def fetch(self, file_path: str, title: str = None) -> ConnectorResult:
        parsed = self._parser.parse_pdf(file_path, title=title)
        return ConnectorResult(
            content=parsed.content,
            title=parsed.title,
            source_type=self.source_type,
            source_url=file_path,
            sha256=parsed.sha256,
            metadata=parsed.metadata,
            sections=parsed.sections,
        )
