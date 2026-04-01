"""
Enterprise connector stubs.

These connectors implement the BaseConnector interface but are not yet
connected to live systems. They demonstrate architectural readiness for
integration with institutional data ecosystems.

To activate a connector:
  1. Install the relevant SDK (e.g., `msal`, `office365-rest-python-client`)
  2. Add credentials to config.py / environment variables
  3. Implement the fetch() body — the rest of the pipeline requires no changes

Intended integrations:
  - SharePointConnector  : Microsoft SharePoint / OneDrive document libraries
  - DataverseConnector   : Microsoft Dataverse structured tables (e.g., HR, student records)
  - ConfluenceConnector  : Atlassian Confluence knowledge bases
  - DatabaseConnector    : Internal relational databases (PostgreSQL, MSSQL, etc.)
"""
from app.connectors.base import BaseConnector, ConnectorResult


class SharePointConnector(BaseConnector):
    """
    Connector for Microsoft SharePoint / OneDrive document libraries.

    Intended use: ingest policy documents, procedural guides, internal memos,
    or any content stored in an institution's SharePoint tenant.

    Required config (not yet wired):
        SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET,
        SHAREPOINT_SITE_URL
    """
    source_type = "sharepoint"

    async def fetch(self, site_url: str, file_path: str, **kwargs) -> ConnectorResult:
        raise NotImplementedError(
            "SharePointConnector is not yet active. "
            "Install 'office365-rest-python-client' and configure SHAREPOINT_* env vars."
        )


class DataverseConnector(BaseConnector):
    """
    Connector for Microsoft Dataverse structured records.

    Intended use: pull structured institutional data (course catalogues,
    departmental records, form submissions) into the RAG pipeline.

    Required config (not yet wired):
        DATAVERSE_URL, DATAVERSE_TENANT_ID, DATAVERSE_CLIENT_ID,
        DATAVERSE_CLIENT_SECRET
    """
    source_type = "dataverse"

    async def fetch(self, table: str, filter_query: str = None, **kwargs) -> ConnectorResult:
        raise NotImplementedError(
            "DataverseConnector is not yet active. "
            "Configure DATAVERSE_* env vars to enable."
        )


class ConfluenceConnector(BaseConnector):
    """
    Connector for Atlassian Confluence knowledge bases.

    Intended use: ingest internal wikis, runbooks, and team documentation.
    """
    source_type = "confluence"

    async def fetch(self, space_key: str, page_id: str = None, **kwargs) -> ConnectorResult:
        raise NotImplementedError(
            "ConfluenceConnector is not yet active. "
            "Install 'atlassian-python-api' and configure CONFLUENCE_* env vars."
        )


class DatabaseConnector(BaseConnector):
    """
    Generic connector for internal relational databases.

    Intended use: pull structured records (faculty directories, course info,
    policy tables) from existing institutional databases into the RAG pipeline.
    """
    source_type = "database"

    async def fetch(self, query: str, connection_string: str = None, **kwargs) -> ConnectorResult:
        raise NotImplementedError(
            "DatabaseConnector is not yet active. "
            "Provide a connection_string and SQL query to enable."
        )
