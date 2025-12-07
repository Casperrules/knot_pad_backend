from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional
from datetime import datetime
from bson import ObjectId
from auth import get_current_user, get_optional_user, get_current_admin
from config import get_settings
from s3_storage import s3_storage
import uuid
import os
import logging
from pathlib import Path
from models import (
    User,
    VideoCreate,
    VideoUpdate,
    VideoResponse,
    VideoListResponse,
    VideoApproval,
    StoryStatus,
)
from database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/videos", tags=["videos"])
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

# Ensure upload directory exists (only for local storage)
if not settings.use_s3:
    Path(settings.video_upload_dir).mkdir(parents=True, exist_ok=True)


def allowed_video_file(filename: str) -> bool:
    """Check if video file extension is allowed"""
    allowed = settings.allowed_video_extensions.split(',')
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


@router.post("/upload-video", response_model=dict)
@limiter.limit("10/hour")
async def upload_video_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a video file to S3 or local storage"""
    if not allowed_video_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {settings.allowed_video_extensions}"
        )
    
    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.max_video_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.max_video_size / 1024 / 1024}MB"
        )
    
    # Read file content
    file_content = await file.read()
    
    # Upload based on configuration
    if settings.use_s3:
        try:
            # Upload to S3 (returns S3 key, not URL)
            s3_key = s3_storage.upload_file(
                file_content=file_content,
                filename=file.filename,
                content_type=file.content_type or "video/mp4",
                folder="videos"
            )
            # Store S3 key, not URL (for security)
            return {"url": f"s3://{s3_key}"}
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload to S3: {str(e)}"
            )
    else:
        # Local storage (development)
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(settings.video_upload_dir, unique_filename)
        
        # Save file locally
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        return {"url": f"/uploads/videos/{unique_filename}"}


def video_helper(video: dict) -> dict:
    """Convert MongoDB video document to response format"""
    video_url = video["video_url"]
    
    # Convert S3 key to pre-signed URL if needed
    if settings.use_s3 and video_url.startswith("s3://"):
        s3_key = video_url.replace("s3://", "")
        try:
            video_url = s3_storage.get_presigned_url(s3_key, expiration=86400)  # 24 hours
        except Exception as e:
            logger.error(f"Failed to generate pre-signed URL for video: {e}")
            video_url = ""  # Fallback to empty string
    
    return {
        "id": str(video["_id"]),
        "video_url": video_url,
        "caption": video["caption"],
        "tags": video.get("tags", []),
        "mature_content": video.get("mature_content", False),
        "author_id": video["author_id"],
        "author_anonymous_name": video["author_anonymous_name"],
        "likes": video.get("likes", 0),
        "views": video.get("views", 0),
        "status": video.get("status", "draft"),
        "created_at": video["created_at"],
        "updated_at": video["updated_at"],
        "published_at": video.get("published_at"),
        "rejection_reason": video.get("rejection_reason"),
    }


@router.post("/", response_model=VideoResponse)
async def create_video(
    video_data: VideoCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Create a new video"""
    now = datetime.utcnow()
    
    video = {
        "video_url": video_data.video_url,
        "caption": video_data.caption,
        "tags": video_data.tags,
        "mature_content": video_data.mature_content,
        "author_id": str(current_user["_id"]),
        "author_anonymous_name": current_user["anonymous_name"],
        "likes": 0,
        "liked_by": [],
        "views": 0,
        "status": StoryStatus.APPROVED,
        "created_at": now,
        "updated_at": now,
    }
    
    result = await db.videos.insert_one(video)
    video["_id"] = result.inserted_id
    
    # Award 1 point to author for creating a video
    await db.users.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$inc": {"points": 1}}
    )
    
    return VideoResponse(**video_helper(video))


@router.get("/", response_model=VideoListResponse)
async def get_videos(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_optional_user),
    db = Depends(get_database),
):
    """Get videos feed"""
    skip = (page - 1) * page_size
    
    # Base query - only show approved videos for public feed
    query = {"status": StoryStatus.APPROVED}
    
    if search:
        query["$or"] = [
            {"caption": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]
    
    cursor = db.videos.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    videos = await cursor.to_list(length=page_size)
    
    total = await db.videos.count_documents(query)
    
    video_responses = [VideoResponse(**video_helper(video)) for video in videos]
    
    return VideoListResponse(videos=video_responses, total=total)


@router.get("/my-videos", response_model=VideoListResponse)
async def get_my_videos(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Get current user's videos"""
    videos = await db.videos.find({"author_id": str(current_user["_id"])}).sort("created_at", -1).to_list(length=None)
    
    total = len(videos)
    video_responses = [VideoResponse(**video_helper(video)) for video in videos]
    
    return VideoListResponse(videos=video_responses, total=total)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    db = Depends(get_database),
):
    """Get a specific video by ID"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Increment view count
    await db.videos.update_one(
        {"_id": ObjectId(video_id)},
        {"$inc": {"views": 1}}
    )
    video["views"] = video.get("views", 0) + 1
    
    return VideoResponse(**video_helper(video))


@router.put("/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: str,
    video_data: VideoUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Update a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if user is the author
    if video["author_id"] != str(current_user["_id"]):
        raise HTTPException(
            status_code=403, detail="You can only edit your own videos"
        )
    
    update_data = {}
    if video_data.caption is not None:
        update_data["caption"] = video_data.caption
    if video_data.tags is not None:
        update_data["tags"] = video_data.tags
    if video_data.mature_content is not None:
        update_data["mature_content"] = video_data.mature_content
    
    update_data["updated_at"] = datetime.utcnow()
    
    await db.videos.update_one({"_id": ObjectId(video_id)}, {"$set": update_data})
    
    updated_video = await db.videos.find_one({"_id": ObjectId(video_id)})
    return VideoResponse(**video_helper(updated_video))


@router.delete("/{video_id}")
async def delete_video(
    video_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Delete a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if user is the author or admin
    if video["author_id"] != str(current_user["_id"]) and current_user["role"] != "admin":
        raise HTTPException(
            status_code=403, detail="You can only delete your own videos"
        )
    
    # Delete associated comments
    await db.comments.delete_many({"video_id": video_id})
    
    # Delete the video
    await db.videos.delete_one({"_id": ObjectId(video_id)})
    
    return {"message": "Video deleted successfully"}


@router.post("/{video_id}/like")
async def toggle_like_video(
    video_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Toggle like on a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
@router.post("/{video_id}/like")
async def toggle_video_like(
    video_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Like or unlike a video"""
    try:
        video_obj_id = ObjectId(video_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": video_obj_id})
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    user_id = str(current_user["_id"])
    liked_by = video.get("liked_by", [])
    
    # Check if user already liked this video
    if user_id in liked_by:
        # Unlike: remove user from liked_by array
        await db.videos.update_one(
            {"_id": video_obj_id},
            {
                "$pull": {"liked_by": user_id},
                "$inc": {"likes": -1}
            }
        )
        liked = False
        new_likes = video.get("likes", 0) - 1
        points_earned = 0
    else:
        # Like: add user to liked_by array
        await db.videos.update_one(
            {"_id": video_obj_id},
            {
                "$addToSet": {"liked_by": user_id},
                "$inc": {"likes": 1}
            }
        )
        liked = True
        new_likes = video.get("likes", 0) + 1
        
        # Award points to video author if they reach 1000 likes milestone
        points_earned = 0
        if new_likes > 0 and new_likes % 1000 == 0:
            await db.users.update_one(
                {"_id": ObjectId(video["author_id"])},
                {"$inc": {"points": 1}}
            )
            points_earned = 1
    
    return {
        "liked": liked,
        "total_likes": max(0, new_likes),
        "points_earned": points_earned
    }


@router.get("/{video_id}/liked")
async def check_if_liked(
    video_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """Check if current user has liked a video"""
    try:
        video = await db.videos.find_one({"_id": ObjectId(video_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    user_id = str(current_user["_id"])
    liked_by = video.get("liked_by", [])
    
    return {"liked": user_id in liked_by}


@router.get("/{video_id}/share")
async def get_video_share_link(
    video_id: str,
    request: Request,
    db = Depends(get_database),
):
    """Get shareable link for a video"""
    try:
        video_obj_id = ObjectId(video_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": video_obj_id})
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Generate share URL
    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/videos?v={video_id}"
    
    return {
        "share_url": share_url,
        "caption": video["caption"],
        "description": video.get("caption", "")[:200],  # Truncate to 200 chars
        "author": video["author_anonymous_name"]
    }


