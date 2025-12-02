from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from models import (
    StoryCreate, StoryUpdate, StoryResponse, StoryListResponse, 
    StoryStatus, StoryApproval, StoryImage, UserRole
)
from auth import get_current_user, get_current_admin_user, update_refresh_token_activity
from database import get_database
from config import get_settings
from s3_storage import s3_storage
import os
import uuid
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stories", tags=["stories"])
settings = get_settings()

# Ensure upload directory exists (only for local storage)
if not settings.use_s3:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    allowed = settings.allowed_extensions.split(',')
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def convert_image_urls(images: List[dict]) -> List[dict]:
    """
    Convert S3 keys to pre-signed URLs for secure access
    Local URLs remain unchanged
    """
    if not settings.use_s3:
        return images
    
    converted_images = []
    for img in images:
        img_copy = img.copy()
        url = img_copy.get('url', '')
        
        # If URL starts with s3://, generate pre-signed URL
        if url.startswith('s3://'):
            s3_key = url.replace('s3://', '')
            try:
                img_copy['url'] = s3_storage.get_presigned_url(s3_key, expiration=86400)  # 24 hours
            except Exception as e:
                logger.error(f"Failed to generate pre-signed URL: {e}")
                img_copy['url'] = ''  # Fallback to empty string
        
        converted_images.append(img_copy)
    
    return converted_images


@router.post("/upload-image", response_model=dict)
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Upload an image for a story"""
    await update_refresh_token_activity(current_user["username"], db)
    
    if not allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {settings.allowed_extensions}"
        )
    
    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
                content_type=file.content_type or "image/jpeg"
            )
            # Store S3 key, not URL (for security)
            return {"url": f"s3://{s3_key}"}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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


@router.post("/", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def create_story(
    story: StoryCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Create a new story (saved as draft)"""
    await update_refresh_token_activity(current_user["username"], db)
    
    story_doc = {
        "title": story.title,
        "description": story.description,
        "cover_image": story.cover_image,
        "tags": story.tags,
        "mature_content": story.mature_content,
        "author_id": str(current_user["_id"]),
        "author_anonymous_name": current_user["anonymous_name"],
        "status": StoryStatus.DRAFT,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "published_at": None,
        "rejection_reason": None
    }
    
    result = await db.stories.insert_one(story_doc)
    story_doc["_id"] = str(result.inserted_id)
    
    return StoryResponse(
        id=str(result.inserted_id),
        title=story_doc["title"],
        description=story_doc["description"],
        cover_image=story_doc.get("cover_image"),
        author_anonymous_name=story_doc["author_anonymous_name"],
        tags=story_doc["tags"],
        mature_content=story_doc["mature_content"],
        status=story_doc["status"],
        chapter_count=0,
        total_reads=0,
        created_at=story_doc["created_at"],
        updated_at=story_doc["updated_at"],
        published_at=story_doc["published_at"]
    )


@router.put("/{story_id}", response_model=StoryResponse)
async def update_story(
    story_id: str,
    story: StoryUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Update a story"""
    await update_refresh_token_activity(current_user["username"], db)
    
    # Convert string ID to ObjectId
    try:
        story_object_id = ObjectId(story_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid story ID format"
        )
    
    # Find story
    existing_story = await db.stories.find_one({"_id": story_object_id})
    if not existing_story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Check ownership
    if existing_story["author_id"] != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this story"
        )
    
    # Update fields
    update_data = {"updated_at": datetime.utcnow()}
    if story.title is not None:
        update_data["title"] = story.title
    if story.description is not None:
        update_data["description"] = story.description
    if story.cover_image is not None:
        update_data["cover_image"] = story.cover_image
    if story.tags is not None:
        update_data["tags"] = story.tags
    if story.mature_content is not None:
        update_data["mature_content"] = story.mature_content
    
    await db.stories.update_one(
        {"_id": story_object_id},
        {"$set": update_data}
    )
    
    updated_story = await db.stories.find_one({"_id": story_object_id})
    
    # Get chapter count
    chapter_count = await db.chapters.count_documents({"story_id": story_id})
    
    return StoryResponse(
        id=str(updated_story["_id"]),
        title=updated_story["title"],
        description=updated_story["description"],
        cover_image=updated_story.get("cover_image"),
        author_anonymous_name=updated_story["author_anonymous_name"],
        tags=updated_story["tags"],
        mature_content=updated_story.get("mature_content", False),
        status=updated_story["status"],
        chapter_count=chapter_count,
        total_reads=updated_story.get("total_reads", 0),
        created_at=updated_story["created_at"],
        updated_at=updated_story["updated_at"],
        published_at=updated_story.get("published_at"),
        rejection_reason=updated_story.get("rejection_reason")
    )


@router.delete("/{story_id}")
async def delete_story(
    story_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Delete a story"""
    await update_refresh_token_activity(current_user["username"], db)
    
    # Convert string ID to ObjectId
    try:
        story_object_id = ObjectId(story_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid story ID format"
        )
    
    story = await db.stories.find_one({"_id": story_object_id})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Only author or admin can delete
    if story["author_id"] != str(current_user["_id"]) and current_user["role"] != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this story"
        )
    
    await db.stories.delete_one({"_id": story_object_id})
    
    # Delete all chapters for this story
    await db.chapters.delete_many({"story_id": story_id})
    
    # Delete all comments for this story
    await db.comments.delete_many({"story_id": story_id})
    
    return {"message": "Story deleted successfully"}


@router.get("/feed", response_model=StoryListResponse)
async def get_feed(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    db=Depends(get_database)
):
    """Get stories feed (public endpoint)"""
    skip = (page - 1) * page_size
    
    # Build query with search
    query = {}
    
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
            {"author_anonymous_name": {"$regex": search, "$options": "i"}}
        ]
    
    # Get approved stories
    cursor = db.stories.find(query).sort("published_at", -1).skip(skip).limit(page_size)
    stories = await cursor.to_list(length=page_size)
    
    total = await db.stories.count_documents(query)
    
    story_responses = []
    for story in stories:
        chapter_count = await db.chapters.count_documents({"story_id": str(story["_id"])})
        story_responses.append(StoryResponse(
            id=str(story["_id"]),
            title=story["title"],
            description=story.get("description", ""),
            cover_image=story.get("cover_image"),
            author_anonymous_name=story["author_anonymous_name"],
            author_id=story.get("author_id"),
            tags=story["tags"],
            mature_content=story.get("mature_content", False),
            status=story["status"],
            chapter_count=chapter_count,
            total_reads=story.get("total_reads", 0),
            created_at=story["created_at"],
            updated_at=story["updated_at"],
            published_at=story.get("published_at")
        ))
    
    return StoryListResponse(
        stories=story_responses,
        total=total
    )


@router.get("/author/{author_id}", response_model=StoryListResponse)
async def get_author_stories(
    author_id: str,
    page: int = 1,
    page_size: int = 10,
    db=Depends(get_database)
):
    """Get all approved stories by a specific author (public endpoint)"""
    skip = (page - 1) * page_size
    
    cursor = db.stories.find(query).sort("published_at", -1).skip(skip).limit(page_size)
    stories = await cursor.to_list(length=page_size)
    
    total = await db.stories.count_documents(query)
    
    story_responses = []
    for story in stories:
        chapter_count = await db.chapters.count_documents({"story_id": str(story["_id"])})
        story_responses.append(StoryResponse(
            id=str(story["_id"]),
            title=story["title"],
            description=story.get("description", ""),
            cover_image=story.get("cover_image"),
            author_anonymous_name=story["author_anonymous_name"],
            author_id=story.get("author_id"),
            tags=story["tags"],
            mature_content=story.get("mature_content", False),
            status=story["status"],
            chapter_count=chapter_count,
            total_reads=story.get("total_reads", 0),
            created_at=story["created_at"],
            updated_at=story["updated_at"],
            published_at=story.get("published_at")
        ))
    
    return StoryListResponse(
        stories=story_responses,
        total=total
    )


@router.get("/my-stories", response_model=StoryListResponse)
async def get_my_stories(
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Get current user's stories"""
    await update_refresh_token_activity(current_user["username"], db)
    
    skip = (page - 1) * page_size
    
    cursor = db.stories.find({"author_id": str(current_user["_id"])}).sort("updated_at", -1).skip(skip).limit(page_size)
    stories = await cursor.to_list(length=page_size)
    
    total = await db.stories.count_documents({"author_id": str(current_user["_id"])})
    
    story_responses = []
    for story in stories:
        chapter_count = await db.chapters.count_documents({"story_id": str(story["_id"])})
        story_responses.append(StoryResponse(
            id=str(story["_id"]),
            title=story["title"],
            description=story.get("description", ""),
            cover_image=story.get("cover_image"),
            author_anonymous_name=story["author_anonymous_name"],
            tags=story["tags"],
            mature_content=story.get("mature_content", False),
            status=story["status"],
            chapter_count=chapter_count,
            total_reads=story.get("total_reads", 0),
            created_at=story["created_at"],
            updated_at=story["updated_at"],
            published_at=story.get("published_at"),
            rejection_reason=story.get("rejection_reason")
        ))
    
    return StoryListResponse(
        stories=story_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Get a single story by ID"""
    await update_refresh_token_activity(current_user["username"], db)
    
    # Convert string ID to ObjectId
    try:
        story_object_id = ObjectId(story_id)
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid story ID format"
        )
    
    story = await db.stories.find_one({"_id": story_object_id})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Only approved stories are visible to all, others only to author and admin
    if story["status"] != StoryStatus.APPROVED:
        if story["author_id"] != str(current_user["_id"]) and current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this story"
            )
    
    # Get chapter count
    chapter_count = await db.chapters.count_documents({"story_id": story_id})
    
    return StoryResponse(
        id=str(story["_id"]),
        title=story["title"],
        description=story.get("description", ""),
        cover_image=story.get("cover_image"),
        author_anonymous_name=story["author_anonymous_name"],
        author_id=story.get("author_id"),
        tags=story["tags"],
        mature_content=story.get("mature_content", False),
        status=story["status"],
        chapter_count=chapter_count,
        total_reads=story.get("total_reads", 0),
        created_at=story["created_at"],
        updated_at=story["updated_at"],
        published_at=story.get("published_at"),
        rejection_reason=story.get("rejection_reason")
    )


@router.get("/author/{author_id}", response_model=StoryListResponse)
async def get_author_stories(
    author_id: str,
    page: int = 1,
    page_size: int = 10,
    db=Depends(get_database)
):
    """Get all approved stories by a specific author (public endpoint)"""
    skip = (page - 1) * page_size
    
    # Get approved stories by author
    query = {"author_id": author_id, "status": StoryStatus.APPROVED}
    cursor = db.stories.find(query).sort("published_at", -1).skip(skip).limit(page_size)
    stories = await cursor.to_list(length=page_size)
    
    total = await db.stories.count_documents(query)
    
    story_responses = [
        StoryResponse(
            id=str(story["_id"]),
            title=story["title"],
            content=story["content"],
            author_anonymous_name=story["author_anonymous_name"],
            author_id=story["author_id"],
            images=[StoryImage(**img) for img in convert_image_urls(story["images"])],
            tags=story["tags"],
            status=story["status"],
            created_at=story["created_at"],
            updated_at=story["updated_at"],
            published_at=story.get("published_at")
        )
        for story in stories
    ]
    
    return StoryListResponse(
        stories=story_responses,
        total=total,
        page=page,
        page_size=page_size
    )

