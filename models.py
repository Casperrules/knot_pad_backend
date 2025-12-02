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


# User Models
class UserBase(BaseModel):
    username: Optional[str] = None
    anonymous_name: str
    email: Optional[str] = None


class UserCreate(BaseModel):
    username: Optional[str] = None
    password: str
    email: Optional[str] = None
    anonymous_name: Optional[str] = None


class UserLogin(BaseModel):
    password: str
    username: Optional[str] = None
    email: Optional[str] = None


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
    description: str  # Story description/summary
    cover_image: Optional[str] = None  # Story cover image
    tags: List[str] = []
    mature_content: bool = False  # Replaces age restriction


class StoryCreate(StoryBase):
    pass


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[List[str]] = None
    mature_content: Optional[bool] = None


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


# Response Models
class UserResponse(BaseModel):
    id: str
    username: Optional[str] = None
    anonymous_name: str
    role: UserRole
    created_at: datetime


class StoryResponse(BaseModel):
    id: str
    title: str
    description: str
    cover_image: Optional[str] = None
    author_anonymous_name: str
    author_id: Optional[str] = None
    tags: List[str]
    status: StoryStatus
    mature_content: bool
    chapter_count: int = 0
    total_reads: int = 0
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class StoryListResponse(BaseModel):
    stories: List[StoryResponse]
    total: int


# Chapter Models
class ChapterBase(BaseModel):
    title: str
    content: str
    chapter_number: int
    story_id: str


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    chapter_number: Optional[int] = None


class Chapter(ChapterBase):
    id: str
    created_at: datetime
    updated_at: datetime
    published: bool = False

    class Config:
        from_attributes = True


class ChapterResponse(BaseModel):
    id: str
    title: str
    content: str
    chapter_number: int
    story_id: str
    created_at: datetime
    updated_at: datetime
    published: bool


# Comment Models
class CommentBase(BaseModel):
    content: str
    story_id: Optional[str] = None
    video_id: Optional[str] = None  # Comment on video
    chapter_id: Optional[str] = None  # Comment on specific chapter
    selected_text: Optional[str] = None  # Text user highlighted
    text_position: Optional[int] = None  # Character position in chapter
    parent_comment_id: Optional[str] = None  # For nested replies


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: str
    user_id: str
    anonymous_name: str
    upvotes: int = 0
    downvotes: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CommentResponse(BaseModel):
    id: str
    content: str
    story_id: Optional[str] = None
    video_id: Optional[str] = None
    chapter_id: Optional[str] = None
    selected_text: Optional[str] = None
    text_position: Optional[int] = None
    parent_comment_id: Optional[str] = None
    user_id: str
    anonymous_name: str
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime
    replies: List["CommentResponse"] = []  # Nested replies


# OTP Models
class OTPBase(BaseModel):
    email: str


class OTPCreate(OTPBase):
    pass


class OTP(OTPBase):
    id: str
    code: str
    created_at: datetime
    expires_at: datetime
    used: bool = False

    class Config:
        from_attributes = True


class OTPVerify(BaseModel):
    email: str
    code: str


# Video Models
class VideoBase(BaseModel):
    video_url: str
    caption: str
    tags: List[str] = []
    mature_content: bool = False


class VideoCreate(VideoBase):
    pass


class VideoUpdate(BaseModel):
    caption: Optional[str] = None
    tags: Optional[List[str]] = None
    mature_content: Optional[bool] = None


class Video(VideoBase):
    id: str
    author_id: str
    author_anonymous_name: str
    likes: int = 0
    views: int = 0
    status: StoryStatus = StoryStatus.DRAFT
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class VideoResponse(Video):
    pass


class VideoListResponse(BaseModel):
    videos: List[VideoResponse]
    total: int


class VideoLike(BaseModel):
    video_id: str
    user_id: str


class VideoApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
