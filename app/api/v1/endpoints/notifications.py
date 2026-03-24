from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.api.deps import get_db, get_current_user
from app.models.user import User, Notification
from app.schemas.admin import NotificationResponse 

router = APIRouter()


@router.get("", response_model=List[NotificationResponse])
async def get_my_notifications(
    is_read: Optional[bool] = None, # For "All" vs "Unread" tabs
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch notifications for the current logged-in user."""
    query = select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc())
    
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
        
    result = await db.execute(query)
    return result.scalars().all()


@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark one of the user's notifications as read."""
    notification = await db.get(Notification, notification_id)
    
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    
    notification.is_read = True
    db.add(notification)
    await db.commit()
    
    return {"message": "Notification marked as read"}


@router.put("/read-all")
async def mark_all_notifications_as_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all of the user's unread notifications as read."""
    unread_notifications = await db.scalars(
        select(Notification).where(Notification.user_id == current_user.id, Notification.is_read == False)
    )
    
    for notification in unread_notifications:
        notification.is_read = True
        db.add(notification)
        
    await db.commit()
    
    return {"message": "All notifications marked as read"}