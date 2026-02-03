"""
Example usage of the NotificationService for sending backend-to-frontend notifications.

This file demonstrates how to use the NotificationService from different parts
of your application to send real-time notifications to users via WebSocket.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import SessionDep
from app.features.auth.services import get_current_user
from app.features.users.models import User
from .services import NotificationService
from .schemas import NotificationLevel

# Example router to demonstrate notification usage
example_router = APIRouter(tags=["Notifications"], prefix="/notifications")


# ============================================================================
# Example 1: Notify user from API endpoint
# ============================================================================
@example_router.post("/notify-me")
async def notify_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Example: Send a notification to the current user."""
    await NotificationService.notify_user(
        user_id=current_user.id,
        message="This is a test notification!",
        level=NotificationLevel.INFO,
        data={"timestamp": "2024-01-01T00:00:00Z"},
    )
    return {"message": "Notification sent"}


# ============================================================================
# Example 2: Notify user after completing background task
# ============================================================================
async def notify_after_file_upload(user_id: int, project_id: int, filename: str):
    """
    Example: Notify user when file upload processing is complete.
    This could be called from a Celery task or Prefect flow.
    """
    await NotificationService.notify_user(
        user_id=user_id,
        message=f"File '{filename}' has been processed successfully!",
        level=NotificationLevel.SUCCESS,
        data={
            "project_id": project_id,
            "filename": filename,
            "action": "file_upload_complete",
        },
    )


# ============================================================================
# Example 3: Notify all users in a project room
# ============================================================================
async def notify_project_collaborators(project_id: int, message: str):
    """
    Example: Notify all users collaborating on a project.
    Useful when someone adds a comment, updates screening, etc.
    """
    room_name = f"project_{project_id}"
    count = await NotificationService.notify_room(
        room_name=room_name,
        message=message,
        level=NotificationLevel.INFO,
        data={
            "project_id": project_id,
            "action": "project_update",
        },
    )
    return count


# ============================================================================
# Example 4: Broadcast system notifications
# ============================================================================
async def notify_system_maintenance():
    """
    Example: Broadcast a system-wide notification to all connected users.
    """
    await NotificationService.broadcast(
        message="System maintenance scheduled in 10 minutes. Please save your work.",
        level=NotificationLevel.WARNING,
        data={"maintenance_time": "2024-01-01T10:00:00Z"},
    )


# ============================================================================
# Example 5: Conditional notifications based on connection status
# ============================================================================
async def notify_if_online(user_id: int, message: str):
    """
    Example: Only send notification if user is connected.
    Useful to avoid errors when user is offline.
    """
    if NotificationService.is_user_connected(user_id):
        await NotificationService.notify_user(
            user_id=user_id, message=message, level=NotificationLevel.INFO
        )
        return True
    else:
        # User is offline, maybe save to database for later display
        print(f"User {user_id} is offline, notification not sent")
        return False


# ============================================================================
# Example 6: Usage in project upload endpoint
# ============================================================================
@example_router.post("/projects/{project_id}/complete-upload")
async def complete_project_upload(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Example: Endpoint that triggers a notification after processing.
    This demonstrates integration with existing project endpoints.
    """
    # ... do some processing ...

    # Notify the user
    await NotificationService.notify_user(
        user_id=current_user.id,
        message=f"Project {project_id} upload completed successfully!",
        level=NotificationLevel.SUCCESS,
        data={
            "project_id": project_id,
            "action": "upload_complete",
            "redirect_url": f"/projects/{project_id}",
        },
    )

    return {"message": "Upload complete, notification sent"}


# ============================================================================
# Example 7: Error notifications
# ============================================================================
async def notify_processing_error(user_id: int, project_id: int, error_message: str):
    """
    Example: Notify user when an error occurs during background processing.
    """
    await NotificationService.notify_user(
        user_id=user_id,
        message=f"Error processing project {project_id}: {error_message}",
        level=NotificationLevel.ERROR,
        data={
            "project_id": project_id,
            "error": error_message,
            "action": "processing_failed",
        },
    )


# ============================================================================
# Example 8: Progress notifications
# ============================================================================
async def notify_processing_progress(user_id: int, project_id: int, progress: int):
    """
    Example: Send progress updates during long-running operations.
    """
    await NotificationService.notify_user(
        user_id=user_id,
        message=f"Processing project {project_id}: {progress}% complete",
        level=NotificationLevel.INFO,
        data={
            "project_id": project_id,
            "progress": progress,
            "action": "progress_update",
        },
    )


# ============================================================================
# Example 9: Integration with Celery tasks
# ============================================================================
# In your tasks.py file:
"""
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

@celery_app.task
def process_file_task(user_id: int, file_path: str):
    '''Process uploaded file and notify user when complete.'''
    try:
        # Process the file...
        result = process_file(file_path)

        # Notify user of success
        import asyncio
        asyncio.run(NotificationService.notify_user(
            user_id=user_id,
            message="File processing complete!",
            level=NotificationLevel.SUCCESS,
            data={"result": result}
        ))
    except Exception as e:
        # Notify user of error
        import asyncio
        asyncio.run(NotificationService.notify_user(
            user_id=user_id,
            message=f"File processing failed: {str(e)}",
            level=NotificationLevel.ERROR
        ))
"""


# ============================================================================
# Example 10: Get connection status and room info
# ============================================================================
@example_router.get("/connection-status/{user_id}")
async def get_user_connection_status(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Example: Check if a user is currently connected."""
    is_connected = NotificationService.is_user_connected(user_id)
    return {
        "user_id": user_id,
        "connected": is_connected,
        "total_connected_users": len(NotificationService.get_connected_users()),
    }


@example_router.get("/rooms/{room_name}/members")
async def get_room_members(
    room_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Example: Get all users in a specific room."""
    members = NotificationService.get_room_members(room_name)
    return {"room_name": room_name, "member_count": len(members), "member_ids": list(members)}
