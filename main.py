from typing import Any, Dict, Optional
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from .db import get_options_with_available_loads
from .scheduler import check_cooldown, record_email_sent, start_scheduler, stop_scheduler, is_scheduler_running
from .email_service import send_options_email

router = APIRouter()


async def _send_email_task():
    """
    Async task function that the scheduler calls to send emails.
    """
    try:
        # Get org_id from environment or use default
        org_id = os.environ.get("ORG_ID", "01970f4c-c79d-7858-8034-60a265d687e4")
        
        # Query options
        options = get_options_with_available_loads(org_id)
        
        # Check cooldown (as safety)
        can_send, reason = check_cooldown()
        if not can_send:
            print(f"Scheduled email task skipped: {reason}")
            return
        
        # Send email
        email_result = send_options_email(options, org_id=org_id)
        
        if email_result.get("success"):
            record_email_sent()
            print(f"Scheduled email sent successfully with {len(options)} option(s)")
        else:
            print(f"Scheduled email failed: {email_result.get('error')}")
    except Exception as e:
        print(f"Error in scheduled email task: {str(e)}")
        import traceback
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app):
    """
    FastAPI lifespan context manager to start/stop scheduler.
    """
    # Startup: Start scheduler if enabled
    enable_scheduler = os.environ.get("ENABLE_EMAIL_SCHEDULER", "false").lower() == "true"
    interval_minutes = int(os.environ.get("EMAIL_SCHEDULE_INTERVAL_MINUTES", "60"))
    
    if enable_scheduler:
        print(f"Starting email scheduler with {interval_minutes} minute interval...")
        start_scheduler(_send_email_task, interval_minutes=interval_minutes)
    else:
        print("Email scheduler is disabled (set ENABLE_EMAIL_SCHEDULER=true to enable)")
    
    yield
    
    # Shutdown: Stop scheduler
    if is_scheduler_running():
        print("Stopping email scheduler...")
        stop_scheduler()


class SendEmailRequest(BaseModel):
    """Request body for send-email endpoint."""
    org_id: Optional[str] = None


def _get_org_id(body: Optional[Dict[str, Any]]) -> str:
    """Extract org_id from request body or use default."""
    if body and isinstance(body, dict):
        org_id = body.get("org_id")
        if org_id:
            return org_id
    return "01970f4c-c79d-7858-8034-60a265d687e4"


@router.post("/send-email")
async def send_email(request: Optional[SendEmailRequest] = None):
    """
    Sends email with options data (with cooldown check).
    
    Args:
        request: Optional request body containing org_id
        
    Returns:
        JSON response with email result
    """
    try:
        # Get org_id from request or use default
        body = request.dict() if request else {}
        org_id = _get_org_id(body)
        
        # Query options - only returns options for pre-book loads with status='available'
        options = get_options_with_available_loads(org_id)
        
        # Check cooldown
        can_send, reason = check_cooldown()
        
        if not can_send:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "skipped",
                    "reason": reason,
                    "options_count": len(options),
                    "message": "Email not sent due to cooldown period"
                }
            )
        
        # Send email
        email_result = send_options_email(options, org_id=org_id)
        
        if email_result.get("success"):
            record_email_sent()
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "options_count": len(options),
                    "email_result": email_result,
                    "message": f"Email sent successfully with {len(options)} option(s)"
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "options_count": len(options),
                    "error": email_result.get("error"),
                    "message": "Failed to send email"
                }
            )
            
    except ValueError as ve:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Configuration error: {str(ve)}"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )


@router.post("/webhook")
async def webhook(request: Optional[SendEmailRequest] = None):
    """
    Legacy webhook endpoint that sends email.
    Same functionality as /send-email endpoint.
    
    Args:
        request: Optional request body containing org_id
        
    Returns:
        JSON response with email result
    """
    return await send_email(request)


@router.post("/")
async def root(request: Optional[SendEmailRequest] = None):
    """
    Root endpoint that sends email.
    Same functionality as /send-email endpoint.
    
    Args:
        request: Optional request body containing org_id
        
    Returns:
        JSON response with email result
    """
    return await send_email(request)


@router.post("/scheduler/start")
async def start_scheduler_endpoint():
    """
    Manually start the email scheduler.
    
    Returns:
        JSON response with scheduler status
    """
    from .scheduler import start_scheduler, is_scheduler_running
    
    if is_scheduler_running():
        return JSONResponse(
            status_code=200,
            content={
                "status": "already_running",
                "message": "Scheduler is already running"
            }
        )
    
    interval_minutes = int(os.environ.get("EMAIL_SCHEDULE_INTERVAL_MINUTES", "60"))
    success = start_scheduler(_send_email_task, interval_minutes=interval_minutes)
    
    if success:
        return JSONResponse(
            status_code=200,
            content={
                "status": "started",
                "message": f"Scheduler started with {interval_minutes} minute interval"
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to start scheduler. Check if APScheduler is installed."
            }
        )


@router.post("/scheduler/stop")
async def stop_scheduler_endpoint():
    """
    Manually stop the email scheduler.
    
    Returns:
        JSON response with scheduler status
    """
    from .scheduler import stop_scheduler, is_scheduler_running
    
    if not is_scheduler_running():
        return JSONResponse(
            status_code=200,
            content={
                "status": "not_running",
                "message": "Scheduler is not running"
            }
        )
    
    stop_scheduler()
    return JSONResponse(
        status_code=200,
        content={
            "status": "stopped",
            "message": "Scheduler stopped"
        }
    )


@router.get("/scheduler/status")
async def scheduler_status():
    """
    Get the current status of the email scheduler.
    
    Returns:
        JSON response with scheduler status information
    """
    from .scheduler import is_scheduler_running
    
    can_send, reason = check_cooldown()
    interval_minutes = int(os.environ.get("EMAIL_SCHEDULE_INTERVAL_MINUTES", "60"))
    
    return JSONResponse(
        status_code=200,
        content={
            "scheduler_running": is_scheduler_running(),
            "interval_minutes": interval_minutes,
            "cooldown_check": {
                "can_send": can_send,
                "reason": reason if not can_send else "Ready to send"
            },
            "enabled": os.environ.get("ENABLE_EMAIL_SCHEDULER", "false").lower() == "true"
        }
    )

