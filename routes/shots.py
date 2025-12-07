from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Request
from typing import Optional
from datetime import datetime
from bson import ObjectId
import uuid
import os

from models import ShotCreate, ShotUpdate, ShotResponse, ShotListResponse, ShotApproval, StoryStatus
from auth import get_current_user, get_current_admin_user
from database import get_database
from logger_config import logger
from config import get_settings
from s3_storage import s3_storage

settings = get_settings()
router = APIRouter()


def allowed_image_file(filename: str) -> bool:
    """Check if file extension is allowed for images"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in settings.allowed_extensions.split(',')


def convert_s3_url(image_url: str) -> str:
    """
    Convert S3 key (s3://key) to pre-signed URL
    Local URLs remain unchanged
    """
    if not settings.use_s3 or not image_url:
        return image_url
    
    # If URL starts with s3://, generate pre-signed URL
    if image_url.startswith('s3://'):
        s3_key = image_url.replace('s3://', '')
        try:
            return s3_storage.get_presigned_url(s3_key, expiration=86400)  # 24 hours
        except Exception as e:
            logger.error(f"Failed to generate pre-signed URL: {e}")
            return ''  # Fallback to empty string
    
    return image_url


@router.post("/upload-image", response_model=dict)
async def upload_shot_image(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload an image file for a shot to S3 or local storage"""
    if not allowed_image_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {settings.allowed_extensions}"
        )
    
    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.max_file_size / 1024 / 1024}MB"
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
                content_type=file.content_type or "image/jpeg",
                folder="shots"
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
        file_path = os.path.join(settings.upload_dir, unique_filename)
        
        # Save file locally
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        
        return {"url": f"/uploads/{unique_filename}"}


@router.post("/", response_model=ShotResponse, status_code=status.HTTP_201_CREATED)
async def create_shot(
    shot: ShotCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Create a new shot"""
    try:
        shot_dict = {
            "image_url": shot.image_url,
            "caption": shot.caption,
            "tags": shot.tags or [],
            "mature_content": shot.mature_content or False,
            "author_id": current_user["id"],
            "author_anonymous_name": current_user["anonymous_name"],
            "likes": 0,
            "status": StoryStatus.PENDING.value,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await db.shots.insert_one(shot_dict)
        shot_dict["id"] = str(result.inserted_id)
        shot_dict["_id"] = str(result.inserted_id)
        shot_dict["is_liked"] = False
        # Convert S3 URLs to presigned URLs for response
        shot_dict["image_url"] = convert_s3_url(shot_dict.get("image_url", ""))
        
        logger.info(f"Shot created by user {current_user['id']}")
        return ShotResponse(**shot_dict)
    except Exception as e:
        logger.error(f"Error creating shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating shot: {str(e)}")


@router.get("/", response_model=ShotListResponse)
async def get_shots(
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = "approved",
    current_user: Optional[dict] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Get all shots with pagination"""
    try:
        query = {}
        if status_filter:
            query["status"] = status_filter
        
        # Get shots
        shots_cursor = db.shots.find(query).sort("created_at", -1).skip(skip).limit(limit)
        shots = await shots_cursor.to_list(length=limit)
        
        # Get user's liked shots if authenticated
        user_liked_shots = []
        if current_user:
            user_likes = await db.user_liked_posts.find_one({"user_id": current_user["id"]})
            user_liked_shots = user_likes.get("liked_shots", []) if user_likes else []
        
        # Format response
        formatted_shots = []
        for shot in shots:
            shot["id"] = str(shot["_id"])
            shot["is_liked"] = str(shot["_id"]) in user_liked_shots
            # Convert S3 URLs to presigned URLs
            shot["image_url"] = convert_s3_url(shot.get("image_url", ""))
            formatted_shots.append(ShotResponse(**shot))
        
        total = await db.shots.count_documents(query)
        
        return ShotListResponse(shots=formatted_shots, total=total)
    except Exception as e:
        logger.error(f"Error fetching shots: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching shots: {str(e)}")


@router.get("/my-shots", response_model=ShotListResponse)
async def get_my_shots(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Get current user's shots"""
    try:
        shots_cursor = db.shots.find(
            {"author_id": current_user["id"]}
        ).sort("created_at", -1).skip(skip).limit(limit)
        shots = await shots_cursor.to_list(length=limit)
        
        formatted_shots = []
        for shot in shots:
            shot["id"] = str(shot["_id"])
            shot["is_liked"] = False  # Own shots
            # Convert S3 URLs to presigned URLs
            shot["image_url"] = convert_s3_url(shot.get("image_url", ""))
            formatted_shots.append(ShotResponse(**shot))
        
        total = await db.shots.count_documents({"author_id": current_user["id"]})
        
        return ShotListResponse(shots=formatted_shots, total=total)
    except Exception as e:
        logger.error(f"Error fetching user shots: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching user shots: {str(e)}")


@router.get("/{shot_id}", response_model=ShotResponse)
async def get_shot(
    shot_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Get a specific shot by ID"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        shot["id"] = str(shot["_id"])
        
        # Convert S3 URLs to presigned URLs
        shot["image_url"] = convert_s3_url(shot.get("image_url", ""))
        
        # Check if user liked this shot
        shot["is_liked"] = False
        if current_user:
            user_likes = await db.user_liked_posts.find_one({"user_id": current_user["id"]})
            if user_likes:
                shot["is_liked"] = shot_id in user_likes.get("liked_shots", [])
        
        return ShotResponse(**shot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching shot: {str(e)}")


@router.put("/{shot_id}", response_model=ShotResponse)
async def update_shot(
    shot_id: str,
    shot_update: ShotUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Update a shot"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        # Get existing shot
        existing_shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not existing_shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        # Check ownership
        if existing_shot["author_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to update this shot")
        
        # Update fields
        update_data = {}
        if shot_update.caption is not None:
            update_data["caption"] = shot_update.caption
        if shot_update.tags is not None:
            update_data["tags"] = shot_update.tags
        if shot_update.mature_content is not None:
            update_data["mature_content"] = shot_update.mature_content
        
        update_data["updated_at"] = datetime.utcnow()
        
        await db.shots.update_one(
            {"_id": ObjectId(shot_id)},
            {"$set": update_data}
        )
        
        # Get updated shot
        updated_shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        updated_shot["id"] = str(updated_shot["_id"])
        updated_shot["is_liked"] = False
        # Convert S3 URLs to presigned URLs
        updated_shot["image_url"] = convert_s3_url(updated_shot.get("image_url", ""))
        
        logger.info(f"Shot {shot_id} updated by user {current_user['id']}")
        return ShotResponse(**updated_shot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating shot: {str(e)}")


@router.delete("/{shot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shot(
    shot_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Delete a shot"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        # Get existing shot
        existing_shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not existing_shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        # Check ownership or admin
        is_admin = current_user.get("role") == "admin"
        if existing_shot["author_id"] != current_user["id"] and not is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to delete this shot")
        
        await db.shots.delete_one({"_id": ObjectId(shot_id)})
        
        logger.info(f"Shot {shot_id} deleted by user {current_user['id']}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting shot: {str(e)}")


@router.post("/{shot_id}/like")
async def like_shot(
    shot_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Like or unlike a shot"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        # Get or create user likes document
        user_likes = await db.user_liked_posts.find_one({"user_id": current_user["id"]})
        
        if not user_likes:
            user_likes = {
                "user_id": current_user["id"],
                "liked_stories": [],
                "liked_videos": [],
                "liked_comments": [],
                "liked_shots": [],
                "updated_at": datetime.utcnow()
            }
            await db.user_liked_posts.insert_one(user_likes)
        
        liked_shots = user_likes.get("liked_shots", [])
        
        if shot_id in liked_shots:
            # Unlike
            await db.user_liked_posts.update_one(
                {"user_id": current_user["id"]},
                {
                    "$pull": {"liked_shots": shot_id},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            await db.shots.update_one(
                {"_id": ObjectId(shot_id)},
                {"$inc": {"likes": -1}}
            )
            liked = False
        else:
            # Like
            await db.user_liked_posts.update_one(
                {"user_id": current_user["id"]},
                {
                    "$addToSet": {"liked_shots": shot_id},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
            await db.shots.update_one(
                {"_id": ObjectId(shot_id)},
                {"$inc": {"likes": 1}}
            )
            liked = True
        
        # Get updated shot
        updated_shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        
        return {
            "liked": liked,
            "likes": updated_shot["likes"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error liking shot: {str(e)}")


@router.get("/{shot_id}/share-link")
async def get_shot_share_link(
    shot_id: str,
    db = Depends(get_database)
):
    """Get shareable link for a shot"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        # For now, return a simple URL. Can be enhanced with short URLs later
        share_link = f"http://localhost:3000/shots/{shot_id}"
        
        return {"share_link": share_link}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating share link: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating share link: {str(e)}")


# Admin Routes
@router.put("/{shot_id}/approval", response_model=ShotResponse)
async def approve_or_reject_shot(
    shot_id: str,
    approval: ShotApproval,
    current_user: dict = Depends(get_current_admin_user),
    db = Depends(get_database)
):
    """Approve or reject a shot (admin only)"""
    try:
        if not ObjectId.is_valid(shot_id):
            raise HTTPException(status_code=400, detail="Invalid shot ID")
        
        shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        if not shot:
            raise HTTPException(status_code=404, detail="Shot not found")
        
        update_data = {
            "status": StoryStatus.APPROVED.value if approval.approved else StoryStatus.REJECTED.value,
            "updated_at": datetime.utcnow()
        }
        
        if not approval.approved and approval.rejection_reason:
            update_data["rejection_reason"] = approval.rejection_reason
        
        await db.shots.update_one(
            {"_id": ObjectId(shot_id)},
            {"$set": update_data}
        )
        
        # Get updated shot
        updated_shot = await db.shots.find_one({"_id": ObjectId(shot_id)})
        updated_shot["id"] = str(updated_shot["_id"])
        updated_shot["is_liked"] = False
        # Convert S3 URLs to presigned URLs
        updated_shot["image_url"] = convert_s3_url(updated_shot.get("image_url", ""))
        
        logger.info(f"Shot {shot_id} {'approved' if approval.approved else 'rejected'} by admin {current_user['id']}")
        return ShotResponse(**updated_shot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving/rejecting shot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error approving/rejecting shot: {str(e)}")


@router.get("/pending/all", response_model=ShotListResponse)
async def get_pending_shots(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_admin_user),
    db = Depends(get_database)
):
    """Get all pending shots for admin review"""
    try:
        shots_cursor = db.shots.find(
            {"status": StoryStatus.PENDING.value}
        ).sort("created_at", -1).skip(skip).limit(limit)
        shots = await shots_cursor.to_list(length=limit)
        
        formatted_shots = []
        for shot in shots:
            shot["id"] = str(shot["_id"])
            shot["is_liked"] = False
            # Convert S3 URLs to presigned URLs
            shot["image_url"] = convert_s3_url(shot.get("image_url", ""))
            formatted_shots.append(ShotResponse(**shot))
        
        total = await db.shots.count_documents({"status": StoryStatus.PENDING.value})
        
        return ShotListResponse(shots=formatted_shots, total=total)
    except Exception as e:
        logger.error(f"Error fetching pending shots: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching pending shots: {str(e)}")
