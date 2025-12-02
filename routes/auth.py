from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime, timedelta
from models import UserCreate, UserLogin, Token, RefreshTokenRequest, UserRole, UserResponse, OTPCreate, OTPVerify
from auth import (
    get_password_hash, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    verify_token,
    get_current_user
)
from database import get_database
from config import get_settings
import secrets
import random

router = APIRouter(prefix="/api/auth", tags=["authentication"])
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


def generate_anonymous_name() -> str:
    """Generate a random anonymous name"""
    adjectives = ["Happy", "Clever", "Bright", "Swift", "Calm", "Bold", "Quiet", "Gentle", "Brave", "Wise"]
    nouns = ["Panda", "Fox", "Eagle", "Dolphin", "Tiger", "Owl", "Wolf", "Lion", "Bear", "Hawk"]
    return f"{secrets.choice(adjectives)}{secrets.choice(nouns)}{secrets.randbelow(1000)}"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate, db=Depends(get_database)):
    # Check if username already exists (if provided)
    if user.username:
        existing_user = await db.users.find_one({"username": user.username})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
    
    # Check if email already exists (if provided)
    if user.email:
        existing_email = await db.users.find_one({"email": user.email})
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Generate anonymous name if not provided
    anonymous_name = user.anonymous_name or generate_anonymous_name()
    
    # Ensure anonymous name is unique
    while await db.users.find_one({"anonymous_name": anonymous_name}):
        anonymous_name = generate_anonymous_name()
    
    # Create user document
    user_doc = {
        "username": user.username,
        "email": user.email,
        "hashed_password": get_password_hash(user.password),
        "anonymous_name": anonymous_name,
        "role": UserRole.USER,
        "created_at": datetime.utcnow(),
        "is_active": True
    }
    
    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = str(result.inserted_id)
    
    return UserResponse(
        id=str(result.inserted_id),
        username=user_doc.get("username"),
        anonymous_name=user_doc["anonymous_name"],
        role=user_doc["role"],
        created_at=user_doc["created_at"]
    )


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user: UserLogin, db=Depends(get_database)):
    # Check for admin credentials
    if user.username == settings.admin_username and user.password == settings.admin_password:
        # Check if admin user exists, if not create it
        admin_user = await db.users.find_one({"username": settings.admin_username})
        if not admin_user:
            admin_doc = {
                "username": settings.admin_username,
                "hashed_password": get_password_hash(settings.admin_password),
                "anonymous_name": "Admin",
                "role": UserRole.ADMIN,
                "created_at": datetime.utcnow(),
                "is_active": True
            }
            await db.users.insert_one(admin_doc)
            admin_user = admin_doc
        
        user_role = UserRole.ADMIN
        username = settings.admin_username
    else:
        # Regular user authentication - find by username OR email
        db_user = None
        if user.username:
            db_user = await db.users.find_one({"username": user.username})
        elif user.email:
            db_user = await db.users.find_one({"email": user.email})
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email required"
            )
        
        if not db_user or not verify_password(user.password, db_user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not db_user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        user_role = db_user["role"]
        username = db_user.get("username") or db_user.get("email")
    
    # Create tokens
    access_token = create_access_token(data={"sub": username, "role": user_role})
    refresh_token = create_refresh_token(data={"sub": username, "role": user_role})
    
    # Store refresh token in database
    refresh_token_doc = {
        "username": username,
        "token": refresh_token,
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    }
    
    # Remove old refresh tokens for this user
    await db.refresh_tokens.delete_many({"username": username})
    await db.refresh_tokens.insert_one(refresh_token_doc)
    
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh_token(req: Request, request: RefreshTokenRequest, db=Depends(get_database)):
    # Verify refresh token
    token_data = await verify_token(request.refresh_token, "refresh")
    
    # Check if refresh token exists in database and is not expired
    refresh_token_doc = await db.refresh_tokens.find_one({
        "username": token_data.username,
        "token": request.refresh_token
    })
    
    if not refresh_token_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Check if token has been inactive for more than 1 day
    last_activity = refresh_token_doc.get("last_activity", refresh_token_doc["created_at"])
    if datetime.utcnow() - last_activity > timedelta(days=1):
        # Token expired due to inactivity
        await db.refresh_tokens.delete_one({"_id": refresh_token_doc["_id"]})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to inactivity. Please login again."
        )
    
    # Check if token is expired
    if datetime.utcnow() > refresh_token_doc["expires_at"]:
        await db.refresh_tokens.delete_one({"_id": refresh_token_doc["_id"]})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired. Please login again."
        )
    
    # Create new tokens
    access_token = create_access_token(
        data={"sub": token_data.username, "role": token_data.role}
    )
    new_refresh_token = create_refresh_token(
        data={"sub": token_data.username, "role": token_data.role}
    )
    
    # Update refresh token in database
    await db.refresh_tokens.update_one(
        {"_id": refresh_token_doc["_id"]},
        {
            "$set": {
                "token": new_refresh_token,
                "last_activity": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
            }
        }
    )
    
    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), db=Depends(get_database)):
    # Remove refresh token from database
    await db.refresh_tokens.delete_many({"username": current_user["username"]})
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user["_id"]),
        username=current_user.get("username"),
        anonymous_name=current_user["anonymous_name"],
        role=current_user["role"],
        created_at=current_user["created_at"]
    )


@router.put("/profile")
async def update_profile(
    anonymous_name: str = None,
    email: str = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Update user profile - anonymous name and email"""
    update_fields = {}
    
    if anonymous_name:
        # Check if anonymous name is already taken
        existing = await db.users.find_one({
            "anonymous_name": anonymous_name,
            "_id": {"$ne": current_user["_id"]}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Anonymous name already taken"
            )
        update_fields["anonymous_name"] = anonymous_name
    
    if email:
        # Check if email is already taken
        existing = await db.users.find_one({
            "email": email,
            "_id": {"$ne": current_user["_id"]}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already taken"
            )
        update_fields["email"] = email
    
    if update_fields:
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": update_fields}
        )
    
    return {"message": "Profile updated successfully"}


@router.post("/send-otp")
async def send_otp(otp_request: OTPCreate, db=Depends(get_database)):
    """Send OTP to email for login/registration"""
    # Generate 4-digit OTP
    code = str(random.randint(1000, 9999))
    
    # Delete any existing OTPs for this email
    await db.otps.delete_many({"email": otp_request.email})
    
    # Create OTP document
    otp_doc = {
        "email": otp_request.email,
        "code": code,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "used": False
    }
    
    await db.otps.insert_one(otp_doc)
    
    # TODO: Send email with OTP code
    # For now, return the code in response (REMOVE IN PRODUCTION)
    return {"message": "OTP sent to email", "code": code}


@router.post("/verify-otp", response_model=Token)
async def verify_otp(otp_verify: OTPVerify, db=Depends(get_database)):
    """Verify OTP and login/register user"""
    # Find OTP
    otp = await db.otps.find_one({
        "email": otp_verify.email,
        "code": otp_verify.code,
        "used": False
    })
    
    if not otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP"
        )
    
    # Check if OTP expired
    if datetime.utcnow() > otp["expires_at"]:
        await db.otps.delete_one({"_id": otp["_id"]})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OTP expired"
        )
    
    # Mark OTP as used
    await db.otps.update_one(
        {"_id": otp["_id"]},
        {"$set": {"used": True}}
    )
    
    # Find or create user
    user = await db.users.find_one({"email": otp_verify.email})
    
    if not user:
        # Create new user with email only
        anonymous_name = generate_anonymous_name()
        while await db.users.find_one({"anonymous_name": anonymous_name}):
            anonymous_name = generate_anonymous_name()
        
        user_doc = {
            "email": otp_verify.email,
            "anonymous_name": anonymous_name,
            "role": UserRole.USER,
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        
        result = await db.users.insert_one(user_doc)
        user = await db.users.find_one({"_id": result.inserted_id})
    
    # Create tokens
    identifier = user.get("username") or user["email"]
    access_token = create_access_token(data={"sub": identifier, "role": user["role"]})
    refresh_token = create_refresh_token(data={"sub": identifier, "role": user["role"]})
    
    # Store refresh token
    refresh_token_doc = {
        "username": identifier,
        "token": refresh_token,
        "created_at": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    }
    
    await db.refresh_tokens.delete_many({"username": identifier})
    await db.refresh_tokens.insert_one(refresh_token_doc)
    
    return Token(access_token=access_token, refresh_token=refresh_token)
