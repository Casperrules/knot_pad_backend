# Wattpad Clone Backend

FastAPI-based backend for a blogging application with JWT authentication and MongoDB.

## Features

- **JWT Authentication**: Secure token-based authentication with refresh tokens
- **Role-Based Access Control**: Admin and user roles
- **Story Management**: Create, update, submit, and approve stories
- **Image Upload**: Support for story images
- **Inactivity Timeout**: Automatic session expiration after 1 day of inactivity
- **Admin Approval Workflow**: Stories must be approved by admin before appearing in feed

## Tech Stack

- FastAPI
- MongoDB (Motor async driver)
- JWT (python-jose)
- Bcrypt password hashing
- Pydantic for data validation

## Setup

### Prerequisites

- Python 3.8+
- MongoDB running locally

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your configuration
```

### Environment Variables

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=wattpad_clone
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
UPLOAD_DIR=uploads
MAX_FILE_SIZE=5242880
ALLOWED_EXTENSIONS=jpg,jpeg,png,gif,webp
```

### Run the Server

```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get tokens
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/logout` - Logout (invalidate refresh token)
- `GET /api/auth/me` - Get current user info

### Stories

- `POST /api/stories/` - Create new story (draft)
- `PUT /api/stories/{story_id}` - Update story
- `DELETE /api/stories/{story_id}` - Delete story
- `POST /api/stories/{story_id}/submit` - Submit story for approval
- `GET /api/stories/feed` - Get approved stories
- `GET /api/stories/my-stories` - Get user's own stories
- `GET /api/stories/{story_id}` - Get specific story
- `POST /api/stories/upload-image` - Upload image for story

### Admin Only

- `GET /api/stories/pending` - Get pending stories
- `POST /api/stories/{story_id}/approve` - Approve or reject story

## Security Features

- Password hashing with bcrypt
- JWT tokens with expiration
- Refresh token with inactivity timeout (1 day)
- Role-based access control
- File upload validation
- CORS configuration
- Environment-based configuration

## Admin Credentials

Default admin credentials (change in production):

- Username: `admin`
- Password: `admin123`

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Project Structure

```
backend/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration management
├── database.py          # MongoDB connection
├── models.py            # Pydantic models
├── auth.py              # Authentication utilities
├── routes/
│   ├── __init__.py
│   ├── auth.py          # Auth endpoints
│   └── stories.py       # Story endpoints
├── tests/
│   ├── test_auth.py     # Auth tests
│   └── test_stories.py  # Story tests
├── uploads/             # Uploaded images (created at runtime)
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables
└── .gitignore
```
