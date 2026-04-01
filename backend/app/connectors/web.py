"""Web URL connector."""
from app.connectors.base import BaseConnector, ConnectorResult
from app.rag.parser import DocumentParser


class WebConnector(BaseConnector):
    source_type = "web"

    def __init__(self):
        self._parser = DocumentParser(redact_pii=True)

    async def fetch(self, url: str) -> ConnectorResult:
        parsed = await self._parser.parse_web_url(url)
        return ConnectorResult(
            content=parsed.content,
            title=parsed.title,
            source_type=self.source_type,
            source_url=url,
            sha256=parsed.sha256,
            metadata=parsed.metadata,
            sections=parsed.sections,
        )
