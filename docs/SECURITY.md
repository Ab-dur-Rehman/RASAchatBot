# =============================================================================
# SECURITY GUIDE
# =============================================================================
# Security considerations and best practices for production deployment
# =============================================================================

## Table of Contents

1. [Overview](#overview)
2. [Data Protection](#data-protection)
3. [Authentication & Authorization](#authentication--authorization)
4. [Input Validation](#input-validation)
5. [Prompt Injection Defense](#prompt-injection-defense)
6. [Network Security](#network-security)
7. [Logging & Auditing](#logging--auditing)
8. [Compliance Considerations](#compliance-considerations)

---

## Overview

This document outlines security measures implemented in the chatbot system and recommendations for production deployment.

### Security Principles

1. **Defense in Depth** - Multiple layers of security
2. **Least Privilege** - Minimal permissions for each component
3. **Data Minimization** - Collect only necessary data
4. **Audit Everything** - Log all sensitive operations
5. **Fail Securely** - Default to secure behavior on errors

---

## Data Protection

### PII Handling

The chatbot collects the following PII during interactions:

| Data Type | Purpose | Storage | Retention |
|-----------|---------|---------|-----------|
| Name | Booking identification | PostgreSQL (encrypted) | 1 year |
| Email | Confirmations | PostgreSQL (encrypted) | 1 year |
| Phone | Contact for bookings | PostgreSQL (encrypted) | 1 year |
| Conversation logs | Audit & improvement | PostgreSQL | 90 days |

### Data Encryption

#### At Rest
- PostgreSQL: Enable `pgcrypto` extension for field-level encryption
- Redis: Use encrypted Redis (Redis Enterprise) or deploy in secure VPC
- ChromaDB: Deploy with encrypted volumes

```sql
-- Example: Encrypting PII fields
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt sensitive data
UPDATE bookings SET 
    email = pgp_sym_encrypt(email, 'encryption_key'),
    phone = pgp_sym_encrypt(phone, 'encryption_key');
```

#### In Transit
- Enable TLS for all connections
- Use HTTPS for all API endpoints
- Redis: Enable TLS mode
- PostgreSQL: Require SSL connections

```python
# PostgreSQL with SSL
pool = await asyncpg.create_pool(
    dsn,
    ssl='require',
    ssl_context=ssl_context
)
```

### Data Masking in Logs

The audit logger automatically masks sensitive data:

```python
# rasa/actions/utils/audit_logger.py
SENSITIVE_FIELDS = ['email', 'phone', 'password', 'credit_card']

def _mask_pii(self, data: Dict) -> Dict:
    """Mask sensitive fields in log data."""
    masked = data.copy()
    for field in self.SENSITIVE_FIELDS:
        if field in masked:
            masked[field] = self._mask_value(masked[field], field)
    return masked
```

---

## Authentication & Authorization

### Admin Dashboard

1. **JWT-based Authentication**
   - Tokens expire after 1 hour
   - Refresh tokens valid for 7 days
   - Tokens stored in httpOnly cookies

2. **Role-Based Access Control**
   - `admin` - Full access
   - `editor` - Modify configurations
   - `viewer` - Read-only access

3. **Password Requirements**
   - Minimum 8 characters
   - Mix of uppercase, lowercase, numbers
   - Hashed with bcrypt (cost factor 12)

### API Security

```python
# Example: JWT verification
from jose import jwt, JWTError

async def verify_token(token: str):
    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(status_code=401)
```

### Service-to-Service Auth

- Internal services communicate via private network
- API keys for external integrations
- mTLS for high-security environments

---

## Input Validation

### RASA Layer

```yaml
# domain.yml - Entity validation
entities:
  - email:
      validate: true
  - phone:
      validate: true
```

### Custom Actions

```python
# rasa/actions/utils/validators.py

class InputValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        # Remove non-digits and check length
        digits = re.sub(r'\D', '', phone)
        return 10 <= len(digits) <= 15
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        # Remove potential injection attempts
        return bleach.clean(text, strip=True)
```

### SQL Injection Prevention

- Use parameterized queries (asyncpg handles this)
- Never interpolate user input into SQL

```python
# CORRECT - Parameterized query
await conn.execute(
    "INSERT INTO bookings (name) VALUES ($1)",
    user_name
)

# WRONG - SQL injection risk
# await conn.execute(f"INSERT INTO bookings (name) VALUES ('{user_name}')")
```

---

## Prompt Injection Defense

### Guardrails Implementation

The chatbot includes multi-layer guardrails against prompt injection:

```python
# rasa/actions/utils/guardrails.py

class Guardrails:
    # Patterns that indicate injection attempts
    INJECTION_PATTERNS = [
        r'ignore.*previous.*instructions',
        r'disregard.*above',
        r'you.*are.*now',
        r'new.*instructions',
        r'system.*prompt',
        r'</?(system|user|assistant)>',
    ]
    
    def check_input(self, text: str) -> GuardrailResult:
        # 1. Pattern matching for known attacks
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GuardrailResult(
                    safe=False,
                    reason="potential_injection"
                )
        
        # 2. Length limit
        if len(text) > self.MAX_INPUT_LENGTH:
            return GuardrailResult(safe=False, reason="too_long")
        
        # 3. Encoding anomalies
        if self._has_encoding_anomalies(text):
            return GuardrailResult(safe=False, reason="encoding")
        
        return GuardrailResult(safe=True)
```

### Response Validation

Before sending responses, validate they don't contain:
- System prompt leaks
- Unintended instructions
- Sensitive internal information

```python
def validate_response(self, response: str) -> bool:
    # Check for system prompt leakage
    sensitive_phrases = [
        "my instructions are",
        "i was told to",
        "system prompt",
    ]
    response_lower = response.lower()
    return not any(phrase in response_lower for phrase in sensitive_phrases)
```

---

## Network Security

### Docker Network Isolation

```yaml
# docker-compose.yml
networks:
  chatbot-network:
    driver: bridge
    internal: true  # No external access
  
  public-network:
    driver: bridge
```

### Firewall Rules

Only expose necessary ports:

| Port | Service | Access |
|------|---------|--------|
| 80/443 | NGINX | Public |
| 5005 | RASA | Internal only |
| 5055 | Actions | Internal only |
| 8080 | Admin API | VPN/Internal |
| 5432 | PostgreSQL | Internal only |
| 6379 | Redis | Internal only |

### Rate Limiting

NGINX configuration includes rate limiting:

```nginx
limit_req_zone $binary_remote_addr zone=chat_limit:10m rate=30r/s;
limit_req zone=chat_limit burst=20 nodelay;
```

Application-level rate limiting:

```python
# Per-user limits
RATE_LIMITS = {
    "messages_per_minute": 20,
    "bookings_per_hour": 5,
    "api_calls_per_minute": 60
}
```

---

## Logging & Auditing

### What We Log

| Event Type | Data Logged | Retention |
|------------|-------------|-----------|
| User messages | Intent, entities (masked PII) | 90 days |
| Bot responses | Response template ID | 90 days |
| Task executions | Action name, success/failure | 1 year |
| Admin changes | Who, what, when | Indefinite |
| Security events | Failed auth, injection attempts | 1 year |

### Audit Log Structure

```json
{
    "timestamp": "2024-01-15T10:30:00Z",
    "session_id": "abc123",
    "action_type": "task_execution",
    "action_name": "create_booking",
    "success": true,
    "input_data": {
        "service": "consultation",
        "email": "j***@example.com"
    },
    "metadata": {
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0..."
    }
}
```

### Log Security

- Logs stored in separate database with restricted access
- Automated PII scanning and masking
- Regular log rotation and archival
- Tamper-evident logging (hash chains)

---

## Compliance Considerations

### GDPR

1. **Right to Access** - Users can request their conversation history
2. **Right to Erasure** - Implement data deletion on request
3. **Data Portability** - Export user data in JSON format
4. **Consent** - Clear privacy notice before conversation

```python
# Data deletion endpoint
@router.delete("/user-data/{user_id}")
async def delete_user_data(user_id: str):
    await conn.execute("DELETE FROM audit_logs WHERE session_id = $1", user_id)
    await conn.execute("DELETE FROM bookings WHERE user_id = $1", user_id)
    return {"status": "deleted"}
```

### SOC 2

Relevant controls:
- CC6.1: Logical access security
- CC6.6: Data protection
- CC7.2: System monitoring
- CC8.1: Change management

### HIPAA (if handling health data)

- Enable encryption everywhere
- Implement access audit trails
- Sign BAA with cloud providers
- Regular security assessments

---

## Security Checklist

### Before Production

- [ ] Change all default passwords
- [ ] Enable TLS for all connections
- [ ] Configure proper CORS origins
- [ ] Set up rate limiting
- [ ] Enable audit logging
- [ ] Configure log rotation
- [ ] Set up monitoring alerts
- [ ] Perform security scan
- [ ] Document incident response plan

### Regular Maintenance

- [ ] Weekly: Review security logs
- [ ] Monthly: Update dependencies
- [ ] Quarterly: Penetration testing
- [ ] Annually: Security audit

---

## Incident Response

### Security Incident Types

1. **Data Breach** - Unauthorized access to PII
2. **Service Compromise** - Attacker gains system access
3. **Injection Attack** - Successful prompt injection
4. **DoS Attack** - Service unavailability

### Response Steps

1. **Detect** - Automated alerts + manual monitoring
2. **Contain** - Isolate affected systems
3. **Eradicate** - Remove threat
4. **Recover** - Restore services
5. **Learn** - Post-incident review

### Contact

Security issues should be reported to: security@your-company.com
