# Security Threat Model

## Overview

This document outlines the security considerations and mitigations for the Wealth Advisor Copilot system, designed for enterprise financial services use.

## Assets to Protect

| Asset | Classification | Impact if Compromised |
|-------|---------------|----------------------|
| Client financial documents | Highly Confidential | Regulatory violation, reputation damage |
| User credentials | Confidential | Account takeover |
| Audit logs | Confidential | Compliance violation |
| API keys (OpenAI, Cohere) | Secret | Service disruption, cost exposure |

## Threat Categories

### 1. Data Leakage

#### 1.1 Cross-Tenant Data Access
**Threat**: User in Tenant A accesses documents from Tenant B

**Mitigations**:
- Every database query includes `tenant_id` filter
- Chunks inherit `tenant_id` from parent document
- All retrievals validate tenant ownership

```python
# Example: Retrieval always filtered
chunks = await retriever.retrieve(
    db=db,
    query=query,
    tenant_id=current_user.tenant_id,  # REQUIRED
    ...
)
```

#### 1.2 Cross-Client Data Access
**Threat**: Advisor accesses wrong client's portfolio

**Mitigations**:
- Optional `client_id` filter on all queries
- Client ownership tracked at document level
- Audit logs capture which client context was used

#### 1.3 PII Exposure
**Threat**: Sensitive personal information indexed and retrievable

**Mitigations**:
- Pre-indexing PII redaction (email, phone, SSN, credit card)
- Pattern-based detection before storage
- Flagging if PII detected in queries

```python
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
    "ssn": r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
}
```

### 2. Prompt Injection

#### 2.1 Jailbreak Attempts
**Threat**: User crafts prompt to bypass safety guidelines

**Mitigations**:
- Strong system prompt with explicit rules
- Intent classification before retrieval
- Post-generation flag checking
- All attempts logged to audit table

#### 2.2 Data Extraction
**Threat**: Prompt tricks model into revealing training data

**Mitigations**:
- Model only sees retrieved chunks, not full corpus
- Grounding enforcement in prompts
- Citation requirement reveals source of all claims

### 3. Hallucination

**Threat**: Model generates plausible but incorrect financial information

**Mitigations**:
- Strict grounding prompt: "Use ONLY provided sources"
- Evidence sufficiency check before generation
- Citation requirement for all claims
- `possible_hallucination` flag for uncited statements
- Confidence scoring (High/Medium/Low)
- Automatic refusal when evidence insufficient

### 4. Financial Advice

**Threat**: System provides personalized investment advice (regulatory violation)

**Mitigations**:
- System prompt explicitly prohibits advice
- Refusal patterns for advice-seeking queries
- `advice_refused` flag in audit logs
- Disclaimer in all communications
- Email template includes mandatory disclaimer

### 5. Authentication & Authorization

#### 5.1 Token Theft
**Threat**: Attacker obtains valid JWT token

**Mitigations**:
- Short token expiration (24h default)
- Token stored in httpOnly cookies (recommended)
- Audit logging includes user context

#### 5.2 Privilege Escalation
**Threat**: Regular user accesses admin functions

**Mitigations**:
- Role-based access control (advisor, admin, compliance)
- Admin endpoints check role
- UI hides unauthorized features

```python
def require_admin(current_user: User):
    if current_user.role not in ["admin", "compliance"]:
        raise HTTPException(status_code=403)
```

### 6. Infrastructure

#### 6.1 API Key Exposure
**Threat**: OpenAI/Cohere keys leaked

**Mitigations**:
- Keys stored in environment variables
- `.env` in `.gitignore`
- Docker secrets for production

#### 6.2 Database Access
**Threat**: Direct database access bypass application security

**Mitigations**:
- Database credentials separate from app secrets
- Network isolation in production
- Connection pooling limits

## Audit Trail

All security-relevant events captured in `audit_logs`:

| Field | Security Purpose |
|-------|-----------------|
| `conversation_id` | Session tracking |
| `user_query` | Detect injection attempts |
| `retrieved_chunk_ids` | Verify data access scope |
| `flags.pii_detected` | PII exposure attempts |
| `flags.advice_refused` | Compliance tracking |
| `flags.possible_hallucination` | Quality assurance |

## Compliance Considerations

### FINRA / SEC
- No personalized advice without proper licensing
- Audit trail for all client interactions
- Document retention (audit_logs)

### GDPR / CCPA
- PII redaction before storage
- Data access scoped to tenant
- Right to deletion (document delete cascades)

### SOC 2
- Access controls (RBAC)
- Audit logging
- Encryption in transit (HTTPS)

## Security Checklist for Production

- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Enable HTTPS (TLS termination)
- [ ] Set short JWT expiration
- [ ] Restrict database network access
- [ ] Enable rate limiting
- [ ] Configure CORS for production domains
- [ ] Set up log aggregation
- [ ] Enable database backups
- [ ] Rotate API keys periodically
- [ ] Conduct penetration testing
