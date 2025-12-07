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
    points: int = 0
    referral_code: Optional[str] = None
    referred_by: Optional[str] = None  # User ID who referred this user
    referral_count: int = 0  # Number of successful referrals


class UserCreate(BaseModel):
    username: Optional[str] = None
    password: str
    email: Optional[str] = None
    anonymous_name: Optional[str] = None
    referral_code: Optional[str] = None  # Code of user who referred them


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
    points: int = 0
    referral_code: str  # User's unique referral code
    referred_by: Optional[str] = None
    referral_count: int = 0
    
    class Config:
        populate_by_name = True


class User(UserBase):
    id: str
    role: UserRole
    created_at: datetime
    is_active: bool
    points: int = 0
    referral_code: str
    referral_count: int = 0


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
    likes: int = 0
    liked_by: List[str] = []  # User IDs who liked this story


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
    likes: int = 0
    liked_by: List[str] = []
    
    class Config:
        populate_by_name = True


class Story(StoryBase):
    id: str
    author_anonymous_name: str
    status: StoryStatus
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    likes: int = 0


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
    likes: int = 0
    is_liked: bool = False  # Whether current user liked this story
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
    likes: int = 0
    liked_by: List[str] = []  # User IDs who liked this comment


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: str
    user_id: str
    anonymous_name: str
    upvotes: int = 0
    downvotes: int = 0
    likes: int = 0
    liked_by: List[str] = []
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
    likes: int = 0
    is_liked: bool = False
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
    likes: int = 0
    liked_by: List[str] = []  # User IDs who liked this video


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
    views: int = 0
    status: StoryStatus = StoryStatus.DRAFT
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class VideoResponse(Video):
    is_liked: bool = False  # Whether current user liked this video


class VideoListResponse(BaseModel):
    videos: List[VideoResponse]
    total: int


class VideoLike(BaseModel):
    video_id: str
    user_id: str


class VideoApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


# Like Models
class LikeRequest(BaseModel):
    """Request to like a story, video, or comment"""
    pass


class LikeResponse(BaseModel):
    """Response after liking/unliking"""
    liked: bool
    total_likes: int
    points_earned: int = 0  # Points earned by author if milestone reached


# User Stats Models
class UserStats(BaseModel):
    """User statistics including points, referrals, and engagement"""
    user_id: str
    username: Optional[str] = None
    anonymous_name: str
    points: int
    referral_code: str
    referral_count: int
    stories_count: int = 0
    videos_count: int = 0
    total_likes_received: int = 0
    total_story_likes: int = 0
    total_video_likes: int = 0
    total_comment_likes: int = 0


class PointsBreakdown(BaseModel):
    """Detailed breakdown of how user earned points"""
    referral_points: int = 0  # referral_count * 10
    story_points: int = 0  # stories_count * 1
    like_points: int = 0  # total_likes_received / 1000
    total_points: int = 0


# Referral Models
class ReferralInfo(BaseModel):
    """Information about user's referral code and stats"""
    referral_code: str
    referral_count: int
    referral_link: str  # Full URL with referral code


class ShareLink(BaseModel):
    """Shareable link for stories and videos"""
    share_url: str
    title: str
    description: str


# User Liked Posts Tracking
class UserLikedPosts(BaseModel):
    """Track all posts a user has liked for AI recommendation"""
    user_id: str
    liked_stories: List[str] = []  # Story IDs
    liked_videos: List[str] = []  # Video IDs
    liked_comments: List[str] = []  # Comment IDs
    liked_shots: List[str] = []  # Shot IDs
    updated_at: datetime


# Shot (Image Post) Models
class ShotCreate(BaseModel):
    image_url: str
    caption: str
    tags: Optional[List[str]] = []
    mature_content: Optional[bool] = False


class ShotUpdate(BaseModel):
    caption: Optional[str] = None
    tags: Optional[List[str]] = None
    mature_content: Optional[bool] = None


class ShotResponse(BaseModel):
    id: str
    image_url: str
    caption: str
    tags: List[str]
    mature_content: bool
    author_anonymous_name: str
    author_id: Optional[str] = None
    likes: int = 0
    is_liked: bool = False
    status: StoryStatus  # draft, pending, approved, rejected
    created_at: datetime
    updated_at: datetime
    rejection_reason: Optional[str] = None


class ShotListResponse(BaseModel):
    shots: List[ShotResponse]
    total: int


class ShotApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None

