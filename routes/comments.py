from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from typing import List
from bson import ObjectId
from models import CommentCreate, CommentResponse
from auth import get_current_user
from database import get_database

router = APIRouter(prefix="/api/comments", tags=["comments"])


def build_comment_tree(comments: List[dict], parent_id: str = None) -> List[CommentResponse]:
    """Build nested comment tree structure"""
    tree = []
    for comment in comments:
        if comment.get("parent_comment_id") == parent_id:
            comment_response = CommentResponse(
                id=str(comment["_id"]),
                content=comment["content"],
                story_id=comment.get("story_id"),
                video_id=comment.get("video_id"),
                chapter_id=comment.get("chapter_id"),
                selected_text=comment.get("selected_text"),
                text_position=comment.get("text_position"),
                parent_comment_id=comment.get("parent_comment_id"),
                user_id=str(comment["user_id"]),
                anonymous_name=comment["anonymous_name"],
                upvotes=comment.get("upvotes", 0),
                downvotes=comment.get("downvotes", 0),
                created_at=comment["created_at"],
                updated_at=comment["updated_at"],
                replies=build_comment_tree(comments, str(comment["_id"]))
            )
            tree.append(comment_response)
    return tree


@router.post("/story/{story_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    story_id: str,
    comment: CommentCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Create a new comment or reply"""
    # Verify story exists
    story = await db.stories.find_one({"_id": ObjectId(story_id)})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # If parent_comment_id provided, verify it exists
    if comment.parent_comment_id:
        parent = await db.comments.find_one({"_id": ObjectId(comment.parent_comment_id)})
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )
    
    # Create comment document
    comment_doc = {
        "content": comment.content,
        "story_id": story_id,
        "chapter_id": comment.chapter_id,
        "selected_text": comment.selected_text,
        "text_position": comment.text_position,
        "parent_comment_id": comment.parent_comment_id,
        "user_id": current_user["_id"],
        "anonymous_name": current_user["anonymous_name"],
        "upvotes": 0,
        "downvotes": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await db.comments.insert_one(comment_doc)
    comment_doc["_id"] = result.inserted_id
    
    return CommentResponse(
        id=str(result.inserted_id),
        content=comment_doc["content"],
        story_id=comment_doc["story_id"],
        chapter_id=comment_doc.get("chapter_id"),
        selected_text=comment_doc.get("selected_text"),
        text_position=comment_doc.get("text_position"),
        parent_comment_id=comment_doc.get("parent_comment_id"),
        user_id=str(comment_doc["user_id"]),
        anonymous_name=comment_doc["anonymous_name"],
        upvotes=comment_doc["upvotes"],
        downvotes=comment_doc["downvotes"],
        created_at=comment_doc["created_at"],
        updated_at=comment_doc["updated_at"],
        replies=[]
    )


@router.get("/story/{story_id}", response_model=List[CommentResponse])
async def get_story_comments(
    story_id: str,
    db = Depends(get_database)
):
    """Get all comments for a story with nested replies"""
    # Verify story exists
    story = await db.stories.find_one({"_id": ObjectId(story_id)})
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Get all comments for this story
    cursor = db.comments.find({"story_id": story_id}).sort("created_at", 1)
    comments = await cursor.to_list(length=None)
    
    # Build nested tree (only return top-level comments)
    return build_comment_tree(comments, parent_id=None)


@router.get("/chapter/{chapter_id}", response_model=List[CommentResponse])
async def get_chapter_comments(
    chapter_id: str,
    db = Depends(get_database)
):
    """Get all comments for a specific chapter with nested replies"""
    # Verify chapter exists
    chapter = await db.chapters.find_one({"_id": ObjectId(chapter_id)})
    if not chapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )
    
    # Get all comments for this chapter
    cursor = db.comments.find({"chapter_id": chapter_id}).sort("text_position", 1)
    comments = await cursor.to_list(length=None)
    
    # Build nested tree (only return top-level comments)
    return build_comment_tree(comments, parent_id=None)


@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    content: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Update a comment (only by owner)"""
    comment = await db.comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership
    if comment["user_id"] != current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment"
        )
    
    # Update comment
    await db.comments.update_one(
        {"_id": ObjectId(comment_id)},
        {
            "$set": {
                "content": content,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    updated = await db.comments.find_one({"_id": ObjectId(comment_id)})
    
    # Get replies for this comment
    cursor = db.comments.find({"story_id": updated["story_id"]}).sort("created_at", 1)
    all_comments = await cursor.to_list(length=None)
    replies = build_comment_tree(all_comments, parent_id=comment_id)
    
    return CommentResponse(
        id=str(updated["_id"]),
        content=updated["content"],
        story_id=updated["story_id"],
        parent_comment_id=updated.get("parent_comment_id"),
        user_id=str(updated["user_id"]),
        anonymous_name=updated["anonymous_name"],
        upvotes=updated["upvotes"],
        downvotes=updated["downvotes"],
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        replies=replies
    )


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Delete a comment (only by owner or admin)"""
    comment = await db.comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership or admin
    if comment["user_id"] != current_user["_id"] and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )
    
    # Delete comment and all its replies
    await delete_comment_recursive(comment_id, db)
    
    return {"message": "Comment deleted successfully"}


async def delete_comment_recursive(comment_id: str, db):
    """Recursively delete comment and all its replies"""
    # Find all replies
    cursor = db.comments.find({"parent_comment_id": comment_id})
    replies = await cursor.to_list(length=None)
    
    # Delete replies recursively
    for reply in replies:
        await delete_comment_recursive(str(reply["_id"]), db)
    
    # Delete the comment itself
    await db.comments.delete_one({"_id": ObjectId(comment_id)})


@router.post("/{comment_id}/vote")
async def vote_comment(
    comment_id: str,
    vote: str,  # "up" or "down"
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Upvote or downvote a comment"""
    if vote not in ["up", "down"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vote must be 'up' or 'down'"
        )
    
    comment = await db.comments.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Update vote count
    field = "upvotes" if vote == "up" else "downvotes"
    await db.comments.update_one(
        {"_id": ObjectId(comment_id)},
        {"$inc": {field: 1}}
    )
    
    return {"message": f"Comment {vote}voted successfully"}


@router.post("/video/{video_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_video_comment(
    video_id: str,
    comment: CommentCreate,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    """Create a new comment on a video"""
    # Verify video exists
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )
    
    # If parent_comment_id provided, verify it exists
    if comment.parent_comment_id:
        parent = await db.comments.find_one({"_id": ObjectId(comment.parent_comment_id)})
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )
    
    # Create comment document
    comment_doc = {
        "content": comment.content,
        "video_id": video_id,
        "parent_comment_id": comment.parent_comment_id,
        "user_id": current_user["_id"],
        "anonymous_name": current_user["anonymous_name"],
        "upvotes": 0,
        "downvotes": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await db.comments.insert_one(comment_doc)
    comment_doc["_id"] = result.inserted_id
    
    return CommentResponse(
        id=str(result.inserted_id),
        content=comment_doc["content"],
        video_id=comment_doc["video_id"],
        story_id=None,
        chapter_id=None,
        selected_text=None,
        text_position=None,
        parent_comment_id=comment_doc.get("parent_comment_id"),
        user_id=str(comment_doc["user_id"]),
        anonymous_name=comment_doc["anonymous_name"],
        upvotes=comment_doc["upvotes"],
        downvotes=comment_doc["downvotes"],
        created_at=comment_doc["created_at"],
        updated_at=comment_doc["updated_at"],
        replies=[]
    )


@router.get("/video/{video_id}", response_model=List[CommentResponse])
async def get_video_comments(
    video_id: str,
    db = Depends(get_database)
):
    """Get all comments for a video with nested replies"""
    # Verify video exists
    video = await db.videos.find_one({"_id": ObjectId(video_id)})
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )
    
    # Get all comments for this video
    cursor = db.comments.find({"video_id": video_id})
    all_comments = await cursor.to_list(length=None)
    
    # Build comment tree
    comment_tree = build_comment_tree(all_comments)
    
    return comment_tree
