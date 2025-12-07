# Backend Tests

This directory contains tests for the FastAPI backend.

## Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_auth.py
pytest tests/test_stories.py
```

## Test Structure

- `test_auth.py`: Tests for authentication endpoints (register, login, refresh token, logout)
- `test_stories.py`: Tests for story CRUD operations and admin approval workflow

## Requirements

- MongoDB running locally on default port (27017)
- Test database will be cleaned up after each test run
