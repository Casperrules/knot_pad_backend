# Monitoring and Logging Setup

This application includes comprehensive logging and monitoring capabilities.

## Features

### 1. Logging

- **Console Logging**: Real-time logs to stdout with INFO level
- **File Logging**: All logs written to daily rotating files (10MB max, 5 backups)
- **Error Logging**: Separate error log file for quick debugging
- **Log Location**: `backend/logs/` directory

Log files:

- `app_YYYYMMDD.log` - All application logs (DEBUG level)
- `error_YYYYMMDD.log` - Error logs only (ERROR level)

### 2. Request Logging

Every HTTP request is logged with:

- Request ID
- Method and path
- Client IP address
- Response status code
- Processing duration
- Headers (excluding sensitive data)

### 3. Performance Monitoring

- **Slow Request Detection**: Automatically logs requests taking > 1 second
- **Request Duration Tracking**: All request durations are tracked
- **Response Headers**: X-Request-ID and X-Process-Time added to responses

### 4. Metrics Collection

In-memory metrics tracking:

- Total request count
- Error counts and rates
- Status code distribution
- Top endpoints by traffic
- Slowest endpoints
- Recent error history

### 5. Monitoring Endpoints

#### Get Metrics Summary

```bash
GET /metrics
```

Returns:

- Total requests and errors
- Error rate percentage
- Status code distribution
- Top 10 endpoints by traffic
- Slowest 10 endpoints with avg duration

#### Get Recent Errors

```bash
GET /metrics/errors
```

Returns the last 50 error requests with details.

## Usage

### Viewing Logs

```bash
# Watch all logs in real-time
tail -f logs/app_*.log

# Watch error logs only
tail -f logs/error_*.log

# Search for specific errors
grep "ERROR" logs/app_*.log

# Search for slow requests
grep "SLOW REQUEST" logs/app_*.log
```

### Checking Metrics

```bash
# Get metrics summary
curl http://localhost:8000/metrics

# Get recent errors
curl http://localhost:8000/metrics/errors
```

### Log Levels

Configure in `logger_config.py`:

- **DEBUG**: Detailed diagnostic information
- **INFO**: General informational messages (default)
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages for serious problems

Change log level:

```python
logger = setup_logging(log_level="DEBUG", log_dir="logs")
```

## Production Considerations

1. **Protect Monitoring Endpoints**: Add authentication to `/metrics` and `/metrics/errors`
2. **Log Rotation**: Logs automatically rotate at 10MB (configurable)
3. **External Monitoring**: Consider integrating with:

   - Sentry for error tracking
   - Datadog for APM
   - CloudWatch for AWS deployments
   - Prometheus + Grafana for metrics visualization

4. **Log Storage**: For production, consider:
   - Centralized logging (ELK stack, CloudWatch Logs)
   - Log aggregation services
   - Long-term log archival

## Example Monitoring Dashboard

Create a simple monitoring script:

```python
import requests
import time

while True:
    response = requests.get("http://localhost:8000/metrics")
    metrics = response.json()

    print(f"\n=== Metrics Report ===")
    print(f"Total Requests: {metrics['total_requests']}")
    print(f"Total Errors: {metrics['total_errors']}")
    print(f"Error Rate: {metrics['error_rate']:.2f}%")
    print(f"\nTop Endpoints:")
    for ep in metrics['top_endpoints'][:5]:
        print(f"  {ep['endpoint']}: {ep['count']} requests, {ep['avg_duration']:.3f}s avg")

    time.sleep(60)  # Update every minute
```

## Troubleshooting

### No logs appearing

- Check `logs/` directory exists and is writable
- Verify log level is not set too high (e.g., ERROR only)
- Check console output for logging errors

### Logs too verbose

- Increase log level to WARNING or ERROR
- Disable DEBUG logging for third-party libraries
- Adjust `uvicorn.access` logger level

### Performance impact

- Metrics are stored in-memory (limited to last 1000 requests)
- File logging is asynchronous
- Minimal overhead (~1-2ms per request)
