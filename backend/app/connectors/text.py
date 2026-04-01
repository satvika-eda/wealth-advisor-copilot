"""Plain text / manual entry connector."""
from app.connectors.base import BaseConnector, ConnectorResult
from app.rag.parser import DocumentParser


class TextConnector(BaseConnector):
    source_type = "text"

    def __init__(self):
        self._parser = DocumentParser(redact_pii=True)

    async def fetch(self, content: str, title: str = "Text Document", source_url: str = None) -> ConnectorResult:
        parsed = self._parser.parse_text(content, title=title, source_url=source_url)
        return ConnectorResult(
            content=parsed.content,
            title=parsed.title,
            source_type=self.source_type,
            source_url=source_url,
            sha256=parsed.sha256,
            metadata=parsed.metadata,
            sections=parsed.sections,
        )
