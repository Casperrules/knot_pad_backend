"""
User stats, referrals, and points management endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging

from auth import get_current_user, get_optional_user
from database import get_database
from models import (
    UserStats,
    PointsBreakdown,
    ReferralInfo,
    ShareLink,
    UserLikedPosts,
)
import secrets

logger = logging.getLogger(__name__)
import string

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def generate_referral_code(length: int = 8) -> str:
    """Generate a unique referral code"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


async def calculate_user_points(user_id: str, db) -> PointsBreakdown:
    """Calculate user's points from all sources"""
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return PointsBreakdown()
    
    # Referral points: 10 points per referral
    referral_points = user.get("referral_count", 0) * 10
    
    # Story points: 1 point per published story
    stories_count = await db.stories.count_documents({
        "author_id": user_id,
        "status": "approved"
    })
    story_points = stories_count * 1  # Make it explicit: 1 point per story
    
    # Like points: 1 point per 1000 likes across all content
    # Get total likes from stories
    story_pipeline = [
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total_likes": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]
    story_likes_result = await db.stories.aggregate(story_pipeline).to_list(1)
    story_likes = story_likes_result[0]["total_likes"] if story_likes_result else 0
    
    # Get total likes from videos
    video_pipeline = [
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total_likes": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]
    video_likes_result = await db.videos.aggregate(video_pipeline).to_list(1)
    video_likes = video_likes_result[0]["total_likes"] if video_likes_result else 0
    
    # Get total likes from comments
    comment_pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total_likes": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]
    comment_likes_result = await db.comments.aggregate(comment_pipeline).to_list(1)
    comment_likes = comment_likes_result[0]["total_likes"] if comment_likes_result else 0
    
    # Get total likes from shots
    shot_pipeline = [
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total_likes": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]
    shot_likes_result = await db.shots.aggregate(shot_pipeline).to_list(1)
    shot_likes = shot_likes_result[0]["total_likes"] if shot_likes_result else 0
    
    total_likes = story_likes + video_likes + comment_likes + shot_likes
    like_points = total_likes // 1000
    
    total_points = referral_points + story_points + like_points
    
    logger.info(f"Points calculation for user {user_id}: stories={stories_count}, story_points={story_points}, story_likes={story_likes}, video_likes={video_likes}, comment_likes={comment_likes}, shot_likes={shot_likes}, total_points={total_points}")
    
    return PointsBreakdown(
        referral_points=referral_points,
        story_points=story_points,
        like_points=like_points,
        total_points=total_points
    )


async def update_user_points(user_id: str, db) -> int:
    """Recalculate and update user's total points"""
    breakdown = await calculate_user_points(user_id, db)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"points": breakdown.total_points}}
    )
    return breakdown.total_points


@router.get("/me/stats", response_model=UserStats)
async def get_my_stats(current_user: dict = Depends(get_current_user), db=Depends(get_database)):
    """Get current user's stats including points, referrals, and content counts"""
    user_id = str(current_user["_id"])  # Convert ObjectId to string
    
    # Get user data
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update points before returning
    await update_user_points(user_id, db)
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    # Count stories
    stories_count = await db.stories.count_documents({
        "author_id": user_id,
        "status": "approved"
    })
    
    # Count videos
    videos_count = await db.videos.count_documents({
        "author_id": user_id,
        "status": "approved"
    })
    
    # Get total likes from all content
    story_likes = await db.stories.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]).to_list(1)
    total_story_likes = story_likes[0]["total"] if story_likes else 0
    
    video_likes = await db.videos.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]).to_list(1)
    total_video_likes = video_likes[0]["total"] if video_likes else 0
    
    comment_likes = await db.comments.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]).to_list(1)
    total_comment_likes = comment_likes[0]["total"] if comment_likes else 0
    
    shot_likes = await db.shots.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$likes", 0]}}}}
    ]).to_list(1)
    total_shot_likes = shot_likes[0]["total"] if shot_likes else 0
    
    return UserStats(
        user_id=user_id,
        username=user.get("username"),
        anonymous_name=user["anonymous_name"],
        points=user.get("points", 0),
        referral_code=user.get("referral_code", ""),
        referral_count=user.get("referral_count", 0),
        stories_count=stories_count,
        videos_count=videos_count,
        total_likes_received=total_story_likes + total_video_likes + total_comment_likes + total_shot_likes,
        total_story_likes=total_story_likes,
        total_video_likes=total_video_likes,
        total_comment_likes=total_comment_likes
    )


@router.get("/me/points", response_model=PointsBreakdown)
async def get_my_points_breakdown(current_user: dict = Depends(get_current_user), db=Depends(get_database)):
    """Get detailed breakdown of how user earned their points"""
    user_id = current_user["_id"]
    return await calculate_user_points(user_id, db)


@router.get("/me/referral", response_model=ReferralInfo)
async def get_my_referral_info(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Get user's referral code and link"""
    user_id = current_user["_id"]
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    referral_code = user.get("referral_code")
    if not referral_code:
        # Generate referral code if user doesn't have one
        referral_code = generate_referral_code()
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"referral_code": referral_code}}
        )
    
    # Use frontend URL for referral link
    from config import get_settings
    settings = get_settings()
    referral_link = f"{settings.frontend_url}/register?ref={referral_code}"
    
    return ReferralInfo(
        referral_code=referral_code,
        referral_count=user.get("referral_count", 0),
        referral_link=referral_link
    )


@router.get("/leaderboard")
async def get_leaderboard(
    limit: int = 50,
    current_user: dict = Depends(get_optional_user),
    db=Depends(get_database)
):
    """Get top users by points"""
    users = await db.users.find(
        {"is_active": True},
        {"username": 1, "anonymous_name": 1, "points": 1, "referral_count": 1}
    ).sort("points", -1).limit(limit).to_list(limit)
    
    leaderboard = []
    for idx, user in enumerate(users, 1):
        leaderboard.append({
            "rank": idx,
            "user_id": str(user["_id"]),
            "anonymous_name": user["anonymous_name"],
            "username": user.get("username"),
            "points": user.get("points", 0),
            "referral_count": user.get("referral_count", 0),
            "is_current_user": str(user["_id"]) == current_user.get("_id", "") if current_user else False
        })
    
    return {"leaderboard": leaderboard, "total": len(leaderboard)}


@router.get("/me/liked-posts", response_model=UserLikedPosts)
async def get_my_liked_posts(current_user: dict = Depends(get_current_user), db=Depends(get_database)):
    """Get all posts the user has liked (for AI recommendations)"""
    user_id = current_user["_id"]
    
    # Get stories liked by user
    liked_stories = await db.stories.find(
        {"liked_by": user_id},
        {"_id": 1}
    ).to_list(None)
    story_ids = [str(story["_id"]) for story in liked_stories]
    
    # Get videos liked by user
    liked_videos = await db.videos.find(
        {"liked_by": user_id},
        {"_id": 1}
    ).to_list(None)
    video_ids = [str(video["_id"]) for video in liked_videos]
    
    # Get comments liked by user
    liked_comments = await db.comments.find(
        {"liked_by": user_id},
        {"_id": 1}
    ).to_list(None)
    comment_ids = [str(comment["_id"]) for comment in liked_comments]
    
    return UserLikedPosts(
        user_id=user_id,
        liked_stories=story_ids,
        liked_videos=video_ids,
        liked_comments=comment_ids,
        updated_at=datetime.utcnow()
    )


@router.get("/{user_id}/stats", response_model=UserStats)
async def get_user_stats(
    user_id: str,
    current_user: dict = Depends(get_optional_user),
    db=Depends(get_database)
):
    """Get public stats for any user"""
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update points
    await update_user_points(user_id, db)
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    
    # Count stories
    stories_count = await db.stories.count_documents({
        "author_id": user_id,
        "status": "approved"
    })
    
    # Count videos
    videos_count = await db.videos.count_documents({
        "author_id": user_id,
        "status": "approved"
    })
    
    # Get total likes
    story_likes = await db.stories.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$likes"}}}
    ]).to_list(1)
    total_story_likes = story_likes[0]["total"] if story_likes else 0
    
    video_likes = await db.videos.aggregate([
        {"$match": {"author_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$likes"}}}
    ]).to_list(1)
    total_video_likes = video_likes[0]["total"] if video_likes else 0
    
    comment_likes = await db.comments.aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "total": {"$sum": "$likes"}}}
    ]).to_list(1)
    total_comment_likes = comment_likes[0]["total"] if comment_likes else 0
    
    return UserStats(
        user_id=user_id,
        username=user.get("username"),
        anonymous_name=user["anonymous_name"],
        points=user.get("points", 0),
        referral_code=user.get("referral_code", ""),
        referral_count=user.get("referral_count", 0),
        stories_count=stories_count,
        videos_count=videos_count,
        total_likes_received=total_story_likes + total_video_likes + total_comment_likes,
        total_story_likes=total_story_likes,
        total_video_likes=total_video_likes,
        total_comment_likes=total_comment_likes
    )
