# Rate Limiting Configuration

The application implements rate limiting to protect against DDoS attacks and abuse.

## Global Rate Limits

All endpoints have default rate limits:

- **100 requests per minute** per IP address
- **1000 requests per hour** per IP address

## Endpoint-Specific Rate Limits

### Authentication Endpoints

#### Registration

- **Endpoint**: `POST /api/auth/register`
- **Limit**: 5 requests per minute
- **Purpose**: Prevent mass account creation and bot registrations

#### Login

- **Endpoint**: `POST /api/auth/login`
- **Limit**: 10 requests per minute
- **Purpose**: Prevent brute force password attacks

#### Token Refresh

- **Endpoint**: `POST /api/auth/refresh`
- **Limit**: 20 requests per minute
- **Purpose**: Allow legitimate token refreshes while preventing token farming

### Content Creation Endpoints

#### Story Creation

- **Endpoint**: `POST /api/stories/`
- **Limit**: 20 requests per hour
- **Purpose**: Prevent spam story creation

#### Video Upload

- **Endpoint**: `POST /api/videos/upload-video`
- **Limit**: 10 requests per hour
- **Purpose**: Prevent excessive video uploads and storage abuse

## Rate Limit Headers

When a rate limit is applied, the following headers are included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1638360000
```

- `X-RateLimit-Limit`: Maximum requests allowed in the time window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the limit resets

## Rate Limit Exceeded Response

When a rate limit is exceeded, the API returns:

**Status Code**: `429 Too Many Requests`

**Response Body**:

```json
{
  "error": "Rate limit exceeded",
  "detail": "100 per 1 minute"
}
```

## Customization

Rate limits can be adjusted in the route decorators:

```python
@limiter.limit("5/minute")  # Strict limit
@limiter.limit("100/hour")  # Hourly limit
@limiter.limit("1000/day")  # Daily limit
```

## IP-Based Limiting

Rate limits are applied based on the client's IP address using `get_remote_address()`.

For applications behind proxies or load balancers, ensure proper headers are forwarded:

- `X-Forwarded-For`
- `X-Real-IP`

## Bypassing Rate Limits

To bypass rate limits for specific IPs (e.g., internal services), you can:

1. Add IP whitelist in `main.py`:

```python
from slowapi import Limiter

def get_remote_address_with_whitelist(request: Request):
    ip = get_remote_address(request)
    whitelist = ["127.0.0.1", "10.0.0.0/8"]
    if ip in whitelist:
        return "whitelist"
    return ip
```

2. Use API keys for authenticated services (not yet implemented)

## Monitoring Rate Limits

Rate limit violations are logged and tracked in the monitoring system:

```
GET /api/monitoring/metrics
```

Look for high counts of 429 status codes in the metrics.

## Production Recommendations

1. **Use Redis for distributed rate limiting** (for multiple server instances):

   ```python
   from slowapi.storage import RedisStorage

   limiter = Limiter(
       key_func=get_remote_address,
       storage_uri="redis://localhost:6379"
   )
   ```

2. **Adjust limits based on traffic patterns** - Monitor metrics and adjust

3. **Implement user-based limits** - For authenticated users, consider per-user limits

4. **Add progressive penalties** - Increase lockout times for repeated violations

5. **Alert on suspicious activity** - Monitor for patterns indicating attacks

## Testing Rate Limits

To test rate limits in development:

```bash
# Test login rate limit
for i in {1..15}; do
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"test","password":"test"}'
  echo "Request $i"
done
```

Expected: First 10 succeed, requests 11-15 return 429.

## Dependencies

- **slowapi**: FastAPI rate limiting library
- **limits**: Rate limiting algorithms
