from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from datetime import datetime
from bson import ObjectId
from auth import get_current_user, get_optional_user, get_current_admin
from models import (
    User,
    VideoCreate,
    VideoUpdate,
    VideoResponse,
    VideoListResponse,
    VideoApproval,
    StoryStatus,
)
from database import db

router = APIRouter(prefix="/api/videos", tags=["videos"])


def video_helper(video: dict) -> dict:
    """Convert MongoDB video document to response format"""
    return {
        "id": str(video["_id"]),
        "video_url": video["video_url"],
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
    current_user: User = Depends(get_current_user),
):
    """Create a new video"""
    now = datetime.utcnow()
    
    video = {
        "video_url": video_data.video_url,
        "caption": video_data.caption,
        "tags": video_data.tags,
        "mature_content": video_data.mature_content,
        "author_id": current_user.id,
        "author_anonymous_name": current_user.anonymous_name,
        "likes": 0,
        "views": 0,
        "status": StoryStatus.APPROVED,
        "created_at": now,
        "updated_at": now,
    }
    
    result = await db.videos.insert_one(video)
    video["_id"] = result.inserted_id
    
    return VideoResponse(**video_helper(video))


@router.get("/", response_model=VideoListResponse)
async def get_videos(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Get videos feed"""
    skip = (page - 1) * page_size
    
    query = {}
    
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
async def get_my_videos(current_user: User = Depends(get_current_user)):
    """Get current user's videos"""
    videos = await db.videos.find({"author_id": current_user.id}).sort("created_at", -1).to_list(length=None)
    
    total = len(videos)
    video_responses = [VideoResponse(**video_helper(video)) for video in videos]
    
    return VideoListResponse(videos=video_responses, total=total)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
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
    current_user: User = Depends(get_current_user),
):
    """Update a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if user is the author
    if video["author_id"] != current_user.id:
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
    current_user: User = Depends(get_current_user),
):
    """Delete a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if user is the author or admin
    if video["author_id"] != current_user.id and current_user.role != "admin":
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
    current_user: User = Depends(get_current_user),
):
    """Toggle like on a video"""
    if not ObjectId.is_valid(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Check if user already liked
    existing_like = await db.video_likes.find_one({
        "video_id": video_id,
        "user_id": current_user.id
    })
    
    if existing_like:
        # Unlike
        await db.video_likes.delete_one({"_id": existing_like["_id"]})
        await db.videos.update_one(
            {"_id": ObjectId(video_id)},
            {"$inc": {"likes": -1}}
        )
        return {"liked": False, "likes": video.get("likes", 1) - 1}
    else:
        # Like
        await db.video_likes.insert_one({
            "video_id": video_id,
            "user_id": current_user.id,
            "created_at": datetime.utcnow()
        })
        await db.videos.update_one(
            {"_id": ObjectId(video_id)},
            {"$inc": {"likes": 1}}
        )
        return {"liked": True, "likes": video.get("likes", 0) + 1}


@router.get("/{video_id}/liked")
async def check_if_liked(
    video_id: str,
    current_user: User = Depends(get_current_user),
):
    """Check if current user has liked a video"""
    like = await db.video_likes.find_one({
        "video_id": video_id,
        "user_id": current_user.id
    })
    
    return {"liked": like is not None}

