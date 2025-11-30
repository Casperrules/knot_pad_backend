from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class StoryStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class GenderCategory(str, Enum):
    BIOLOGICAL_MALE = "biological_male"
    BIOLOGICAL_FEMALE = "biological_female"
    ALL = "all"


# User Models
class UserBase(BaseModel):
    username: str
    anonymous_name: str
    gender_preference: Optional[GenderCategory] = GenderCategory.BIOLOGICAL_FEMALE


class UserCreate(BaseModel):
    username: str
    password: str
    anonymous_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserInDB(UserBase):
    id: str = Field(alias="_id")
    hashed_password: str
    role: UserRole = UserRole.USER
    created_at: datetime
    is_active: bool = True
    
    class Config:
        populate_by_name = True


class User(UserBase):
    id: str
    role: UserRole
    created_at: datetime
    is_active: bool


# Token Models
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[UserRole] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Story Models
class StoryImage(BaseModel):
    url: str
    caption: Optional[str] = None


class StoryBase(BaseModel):
    title: str
    content: str
    images: List[StoryImage] = []
    tags: List[str] = []
    gender_category: GenderCategory = GenderCategory.BIOLOGICAL_FEMALE


class StoryCreate(StoryBase):
    pass


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    images: Optional[List[StoryImage]] = None
    tags: Optional[List[str]] = None
    gender_category: Optional[GenderCategory] = None


class StoryInDB(StoryBase):
    id: str = Field(alias="_id")
    author_id: str
    author_anonymous_name: str
    status: StoryStatus
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    class Config:
        populate_by_name = True


class Story(StoryBase):
    id: str
    author_anonymous_name: str
    status: StoryStatus
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None


class StoryApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
    gender_category: Optional[GenderCategory] = None


# Response Models
class UserResponse(BaseModel):
    id: str
    username: str
    anonymous_name: str
    role: UserRole
    gender_preference: GenderCategory
    created_at: datetime


class StoryResponse(BaseModel):
    id: str
    title: str
    content: str
    author_anonymous_name: str
    author_id: Optional[str] = None
    images: List[StoryImage]
    tags: List[str]
    status: StoryStatus
    gender_category: GenderCategory
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class StoryListResponse(BaseModel):
    stories: List[StoryResponse]
    total: int
    page: int
    page_size: int
