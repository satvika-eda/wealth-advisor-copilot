"""Document parsing for various formats: PDF, HTML, EDGAR filings, text."""
import re
import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import pdfplumber
import trafilatura


@dataclass
class ParsedDocument:
    """Parsed document with content and metadata."""
    content: str
    title: str
    source_type: str
    source_url: Optional[str]
    sha256: str
    metadata: Dict[str, Any]
    sections: List[Dict[str, Any]]  # Structured sections for better chunking


class DocumentParser:
    """Multi-format document parser."""
    
    PII_PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        "ssn": r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
        "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    }
    
    def __init__(self, redact_pii: bool = True):
        self.redact_pii = redact_pii
    
    def compute_sha256(self, content: str) -> str:
        """Compute SHA256 hash for deduplication."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def redact_pii_content(self, text: str) -> tuple[str, bool]:
        """Redact PII from text, return (redacted_text, pii_found)."""
        pii_found = False
        redacted = text
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, redacted, re.IGNORECASE):
                pii_found = True
                redacted = re.sub(pattern, f'[{pii_type.upper()}_REDACTED]', redacted, flags=re.IGNORECASE)
        
        return redacted, pii_found
    
    def parse_pdf(self, file_path: str, title: Optional[str] = None) -> ParsedDocument:
        """Parse PDF document using pdfplumber."""
        sections = []
        full_text = []
        
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    if self.redact_pii:
                        text, _ = self.redact_pii_content(text)
                    
                    sections.append({
                        "page": page_num,
                        "content": text,
                        "heading": f"Page {page_num}",
                    })
                    full_text.append(text)
        
        content = "\n\n".join(full_text)
        doc_title = title or file_path.split("/")[-1]
        
        return ParsedDocument(
            content=content,
            title=doc_title,
            source_type="pdf",
            source_url=file_path,
            sha256=self.compute_sha256(content),
            metadata={"page_count": len(sections)},
            sections=sections,
        )
    
    def parse_html(self, html_content: str, url: Optional[str] = None, title: Optional[str] = None) -> ParsedDocument:
        """Parse HTML content using BeautifulSoup."""
        soup = BeautifulSoup(html_content, 'lxml')
        
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        doc_title = title
        if not doc_title:
            title_tag = soup.find('title')
            doc_title = title_tag.get_text().strip() if title_tag else "Untitled HTML"
        
        sections = []
        current_section = {"heading": "Introduction", "content": [], "level": 0}
        
        for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'div', 'li']):
            if element.name in ['h1', 'h2', 'h3', 'h4']:
                if current_section["content"]:
                    current_section["content"] = " ".join(current_section["content"])
                    sections.append(current_section)
                
                level = int(element.name[1])
                current_section = {
                    "heading": element.get_text().strip(),
                    "content": [],
                    "level": level,
                }
            else:
                text = element.get_text().strip()
                if text and len(text) > 20:  # Skip very short fragments
                    current_section["content"].append(text)
        
        if current_section["content"]:
            current_section["content"] = " ".join(current_section["content"])
            sections.append(current_section)
        
        full_text = soup.get_text(separator=' ', strip=True)
        if self.redact_pii:
            full_text, _ = self.redact_pii_content(full_text)
        
        return ParsedDocument(
            content=full_text,
            title=doc_title,
            source_type="html",
            source_url=url,
            sha256=self.compute_sha256(full_text),
            metadata={"section_count": len(sections)},
            sections=sections,
        )
    
    async def parse_edgar_filing(
        self,
        cik: str,
        filing_type: str = "10-K",
        accession_number: Optional[str] = None,
    ) -> ParsedDocument:
        """
        Parse SEC EDGAR filing by fetching the primary document HTML.

        Uses the submissions JSON to find the most recent filing of the requested
        type and its primary document filename, then fetches the actual HTML filing
        (not just the index cover page).
        """
        base_url = "https://www.sec.gov"
        headers = {
            "User-Agent": "WealthAdvisorCopilot admin@wealthadvisor.local",
            "Accept-Encoding": "gzip, deflate",
        }

        cik_int = int(cik)
        cik_normalized = str(cik_int).zfill(10)

        async with httpx.AsyncClient(timeout=60) as client:
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik_normalized}.json"
            resp = await client.get(submissions_url, headers=headers)
            if resp.status_code != 200:
                raise ValueError(f"Failed to fetch filings for CIK {cik}: {resp.status_code}")

            data = resp.json()
            company_name = data.get("name", "Unknown Company")
            filings = data.get("filings", {}).get("recent", {})

            forms = filings.get("form", [])
            accession_numbers = filings.get("accessionNumber", [])
            primary_documents = filings.get("primaryDocument", [])

            primary_doc = None
            if not accession_number:
                for i, form in enumerate(forms):
                    if form == filing_type:
                        accession_number = accession_numbers[i]
                        primary_doc = primary_documents[i] if i < len(primary_documents) else None
                        break
                if not accession_number:
                    raise ValueError(f"No {filing_type} filings found for CIK {cik}")
            else:
                # Caller provided accession number — find its primary document
                for i, acc in enumerate(accession_numbers):
                    if acc == accession_number:
                        primary_doc = primary_documents[i] if i < len(primary_documents) else None
                        break

            accession_clean = accession_number.replace('-', '')

            # Build filing URL from primary document
            if primary_doc and primary_doc.endswith('.htm'):
                filing_url = f"{base_url}/Archives/edgar/data/{cik_int}/{accession_clean}/{primary_doc}"
            else:
                # Fall back to index JSON to find the primary .htm
                index_url = f"{base_url}/Archives/edgar/data/{cik_int}/{accession_clean}/{accession_number}-index.json"
                idx_resp = await client.get(index_url, headers=headers)
                filing_url = f"{base_url}/Archives/edgar/data/{cik_int}/{accession_clean}/{accession_number}.txt"
                if idx_resp.status_code == 200:
                    for item in idx_resp.json().get("directory", {}).get("item", []):
                        name = item.get("name", "")
                        item_type = item.get("type", "")
                        if item_type == filing_type and name.endswith(".htm"):
                            filing_url = f"{base_url}/Archives/edgar/data/{cik_int}/{accession_clean}/{name}"
                            break

            response = await client.get(filing_url, headers=headers)
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch filing document: {filing_url} ({response.status_code})")

            content = response.text

        soup = BeautifulSoup(content, 'lxml')
        for tag in soup(['script', 'style', 'ix:header', 'ix:hidden']):
            tag.decompose()

        # Prefer trafilatura; fall back to full BS4 extraction (EDGAR iXBRL is trafilatura-hostile)
        text_content = trafilatura.extract(content, include_tables=True)
        if not text_content or len(text_content) < 5000:
            text_content = soup.get_text(separator='\n', strip=True)

        if self.redact_pii:
            text_content, _ = self.redact_pii_content(text_content)

        sections = self._parse_edgar_sections_from_text(text_content)

        return ParsedDocument(
            content=text_content,
            title=f"{company_name} {filing_type}",
            source_type="edgar",
            source_url=filing_url,
            sha256=self.compute_sha256(text_content),
            metadata={
                "cik": cik,
                "filing_type": filing_type,
                "accession_number": accession_number,
                "company_name": company_name,
            },
            sections=sections,
        )
    
    def _parse_edgar_sections_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Split plain-text EDGAR filing into sections by Item headings.
        Falls back to a single large section so fixed-size chunking still runs.
        """
        item_pattern = re.compile(
            r'(?:^|\n)((?:PART\s+[IVX]+|Item\s+\d+[A-Z]?)[.\s][^\n]{0,80})',
            re.IGNORECASE,
        )
        matches = list(item_pattern.finditer(text))

        if len(matches) < 2:
            return [{"heading": "Filing Content", "content": text, "level": 1}]

        sections = []
        for i, match in enumerate(matches):
            heading = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            if section_text:
                sections.append({"heading": heading, "content": section_text, "level": 2})

        return sections

    def _parse_edgar_sections(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse EDGAR-specific sections (Item 1A, Item 7, etc.)."""
        sections = []
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Common 10-K item patterns
        item_patterns = [
            (r'Item\s*1A[.\s]*Risk\s*Factors', 'Item 1A - Risk Factors'),
            (r'Item\s*1[.\s]*Business', 'Item 1 - Business'),
            (r'Item\s*7A?[.\s]*Management', 'Item 7 - Management Discussion'),
            (r'Item\s*8[.\s]*Financial', 'Item 8 - Financial Statements'),
        ]
        
        text = soup.get_text()
        
        for pattern, heading in item_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract surrounding content (simplified)
                start = match.start()
                end = min(start + 50000, len(text))  # Limit section size
                section_text = text[start:end]
                
                sections.append({
                    "heading": heading,
                    "content": section_text[:10000],  # Limit for initial parsing
                    "item": heading.split(' - ')[0].strip(),
                })
        
        return sections
    
    def parse_text(self, text: str, title: str = "Text Document", source_url: Optional[str] = None) -> ParsedDocument:
        """Parse plain text document."""
        if self.redact_pii:
            text, _ = self.redact_pii_content(text)
        
        # Simple section detection by double newlines
        paragraphs = text.split('\n\n')
        sections = [
            {"heading": f"Section {i+1}", "content": p.strip()}
            for i, p in enumerate(paragraphs) if p.strip()
        ]
        
        return ParsedDocument(
            content=text,
            title=title,
            source_type="text",
            source_url=source_url,
            sha256=self.compute_sha256(text),
            metadata={},
            sections=sections,
        )
    
    async def parse_web_url(self, url: str) -> ParsedDocument:
        """Fetch and parse web URL using trafilatura."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            html_content = response.text
        
        extracted = trafilatura.extract(
            html_content,
            include_tables=True,
            include_comments=False,
        )
        
        if not extracted:
            return self.parse_html(html_content, url=url)
        
        if self.redact_pii:
            extracted, _ = self.redact_pii_content(extracted)
        
        soup = BeautifulSoup(html_content, 'lxml')
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else url
        
        return ParsedDocument(
            content=extracted,
            title=title,
            source_type="web",
            source_url=url,
            sha256=self.compute_sha256(extracted),
            metadata={"original_length": len(html_content)},
            sections=[{"heading": "Main Content", "content": extracted}],
        )
