from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from typing import List
from bson import ObjectId
from models import ChapterCreate, ChapterUpdate, ChapterResponse
from auth import get_current_user
from database import get_database

router = APIRouter(prefix="/api/chapters", tags=["chapters"])


@router.post("/", response_model=ChapterResponse, status_code=status.HTTP_201_CREATED)
async def create_chapter(
    chapter: ChapterCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Create a new chapter for a story"""
    # Verify story exists and user is the author
    story = await db.stories.find_one({"_id": ObjectId(chapter.story_id)})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    if str(story["author_id"]) != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to add chapters to this story"
        )
    
    # Check if chapter number already exists for this story
    existing = await db.chapters.find_one({
        "story_id": chapter.story_id,
        "chapter_number": chapter.chapter_number
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chapter {chapter.chapter_number} already exists"
        )
    
    # Create chapter document
    chapter_doc = {
        "title": chapter.title,
        "content": chapter.content,
        "chapter_number": chapter.chapter_number,
        "story_id": chapter.story_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "published": False
    }
    
    result = await db.chapters.insert_one(chapter_doc)
    chapter_doc["_id"] = result.inserted_id
    
    return ChapterResponse(
        id=str(result.inserted_id),
        title=chapter_doc["title"],
        content=chapter_doc["content"],
        chapter_number=chapter_doc["chapter_number"],
        story_id=chapter_doc["story_id"],
        created_at=chapter_doc["created_at"],
        updated_at=chapter_doc["updated_at"],
        published=chapter_doc["published"]
    )


@router.get("/story/{story_id}", response_model=List[ChapterResponse])
async def get_story_chapters(
    story_id: str,
    db = Depends(get_database)
):
    """Get all chapters for a story, ordered by chapter number"""
    # Verify story exists
    story = await db.stories.find_one({"_id": ObjectId(story_id)})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get all chapters for this story
    cursor = db.chapters.find({"story_id": story_id}).sort("chapter_number", 1)
    chapters = await cursor.to_list(length=None)
    
    return [
        ChapterResponse(
            id=str(chapter["_id"]),
            title=chapter["title"],
            content=chapter["content"],
            chapter_number=chapter["chapter_number"],
            story_id=chapter["story_id"],
            created_at=chapter["created_at"],
            updated_at=chapter["updated_at"],
            published=chapter.get("published", False)
        )
        for chapter in chapters
    ]


@router.get("/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    chapter_id: str,
    db = Depends(get_database)
):
    """Get a specific chapter by ID"""
    chapter = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )
    
    return ChapterResponse(
        id=str(chapter["_id"]),
        title=chapter["title"],
        content=chapter["content"],
        chapter_number=chapter["chapter_number"],
        story_id=chapter["story_id"],
        created_at=chapter["created_at"],
        updated_at=chapter["updated_at"],
        published=chapter.get("published", False)
    )


@router.put("/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    chapter_id: str,
    chapter_update: ChapterUpdate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Update a chapter"""
    chapter = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )
    
    # Verify user is the author
    story = await db.stories.find_one({"_id": ObjectId(chapter["story_id"])})
    if str(story["author_id"]) != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this chapter"
        )
    
    # Build update data
    update_data = {"updated_at": datetime.utcnow()}
    if chapter_update.title is not None:
        update_data["title"] = chapter_update.title
    if chapter_update.content is not None:
        update_data["content"] = chapter_update.content
    if chapter_update.chapter_number is not None:
        # Check if new number conflicts
        existing = await db.chapters.find_one({
            "story_id": chapter["story_id"],
            "chapter_number": chapter_update.chapter_number,
            "_id": {"$ne": ObjectId(chapter_id)}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chapter {chapter_update.chapter_number} already exists"
            )
        update_data["chapter_number"] = chapter_update.chapter_number
    
    await db.chapters.update_one(
        {"_id": ObjectId(chapter_id)},
        {"$set": update_data}
    )
    
    updated = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    
    return ChapterResponse(
        id=str(updated["_id"]),
        title=updated["title"],
        content=updated["content"],
        chapter_number=updated["chapter_number"],
        story_id=updated["story_id"],
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        published=updated.get("published", False)
    )


@router.delete("/{chapter_id}")
async def delete_chapter(
    chapter_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Delete a chapter"""
    chapter = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )
    
    # Verify user is the author
    story = await db.stories.find_one({"_id": ObjectId(chapter["story_id"])})
    if str(story["author_id"]) != str(current_user["_id"]) and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this chapter"
        )
    
    # Delete chapter and all its comments
    await db.chapters.delete_one({"_id": ObjectId(chapter_id)})
    await db.comments.delete_many({"chapter_id": chapter_id})
    
    return {"message": "Chapter deleted successfully"}


@router.post("/{chapter_id}/publish")
async def publish_chapter(
    chapter_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Publish a chapter"""
    chapter = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )
    
    # Verify user is the author
    story = await db.stories.find_one({"_id": ObjectId(chapter["story_id"])})
    if str(story["author_id"]) != str(current_user["_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to publish this chapter"
        )
    
    await db.chapters.update_one(
        {"_id": ObjectId(chapter_id)},
        {"$set": {"published": True, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Chapter published successfully"}
