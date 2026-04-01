"""SEC EDGAR connector — wraps the existing DocumentParser.parse_edgar_filing."""
from app.connectors.base import BaseConnector, ConnectorResult
from app.rag.parser import DocumentParser


class EdgarConnector(BaseConnector):
    source_type = "edgar"

    def __init__(self):
        self._parser = DocumentParser(redact_pii=True)

    async def fetch(self, cik: str, filing_type: str = "10-K", accession_number: str = None) -> ConnectorResult:
        parsed = await self._parser.parse_edgar_filing(cik, filing_type, accession_number)
        return ConnectorResult(
            content=parsed.content,
            title=parsed.title,
            source_type=self.source_type,
            source_url=parsed.source_url,
            sha256=parsed.sha256,
            metadata=parsed.metadata,
            sections=parsed.sections,
        )
