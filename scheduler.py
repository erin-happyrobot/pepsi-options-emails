import os
import json
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Callable
from pathlib import Path

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    IntervalTrigger = None


# Cooldown period in minutes (default: 60 minutes / 1 hour)
COOLDOWN_MINUTES = int(os.environ.get("EMAIL_COOLDOWN_MINUTES", "60"))

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None
_send_email_callback: Optional[Callable] = None


def _get_cooldown_file_path() -> Path:
    """
    Get the path to the file that stores the last email sent timestamp.
    
    Returns:
        Path object to the cooldown file
    """
    # Try to use a data directory, or fall back to current directory
    data_dir = os.environ.get("DATA_DIR", "/tmp")
    cooldown_file = Path(data_dir) / "pepsi_options_email_cooldown.json"
    return cooldown_file


def _get_last_email_timestamp() -> datetime | None:
    """
    Read the last email sent timestamp from the cooldown file.
    
    Returns:
        datetime object of last email sent, or None if no record exists
    """
    cooldown_file = _get_cooldown_file_path()
    
    if not cooldown_file.exists():
        return None
    
    try:
        with open(cooldown_file, "r") as f:
            data = json.load(f)
            timestamp_str = data.get("last_email_sent")
            if timestamp_str:
                return datetime.fromisoformat(timestamp_str)
    except (json.JSONDecodeError, ValueError, KeyError, IOError) as e:
        print(f"Error reading cooldown file: {e}")
        return None
    
    return None


def _save_email_timestamp(timestamp: datetime) -> None:
    """
    Save the email sent timestamp to the cooldown file.
    
    Args:
        timestamp: datetime object representing when the email was sent
    """
    cooldown_file = _get_cooldown_file_path()
    
    try:
        # Ensure directory exists
        cooldown_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "last_email_sent": timestamp.isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(cooldown_file, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Error saving cooldown file: {e}")
        # Don't raise - this shouldn't block email sending


def check_cooldown() -> Tuple[bool, str]:
    """
    Check if enough time has passed since the last email was sent.
    
    Returns:
        Tuple of (can_send: bool, reason: str)
        - If can_send is True, reason will be empty string
        - If can_send is False, reason will explain why
    """
    last_email = _get_last_email_timestamp()
    
    if last_email is None:
        # No previous email recorded, so we can send
        return True, ""
    
    # Ensure last_email is timezone-aware
    if last_email.tzinfo is None:
        last_email = last_email.replace(tzinfo=timezone.utc)
    
    # Get current time (timezone-aware)
    now = datetime.now(timezone.utc)
    
    # Calculate time since last email
    time_since_last = now - last_email
    cooldown_duration = timedelta(minutes=COOLDOWN_MINUTES)
    
    # if time_since_last < cooldown_duration:
    #     # Still in cooldown period
    #     remaining_minutes = (cooldown_duration - time_since_last).total_seconds() / 60
    #     return False, f"Cooldown period active. {remaining_minutes:.1f} minutes remaining."
    
    # Cooldown period has passed, can send
    return True, ""


def record_email_sent() -> None:
    """
    Record that an email was sent (updates the timestamp).
    Should be called after successfully sending an email.
    """
    now = datetime.now(timezone.utc)
    _save_email_timestamp(now)


async def _scheduled_email_task():
    """
    Scheduled task that runs periodically to send emails.
    This function is called by the scheduler.
    """
    if _send_email_callback is None:
        print("Warning: No email callback registered for scheduled task")
        return
    
    try:
        print(f"Scheduled email task running at {datetime.now(timezone.utc).isoformat()}")
        
        # Check cooldown before sending (as a safety mechanism)
        can_send, reason = check_cooldown()
        if not can_send:
            print(f"Scheduled email skipped due to cooldown: {reason}")
            return
        
        # Call the email sending callback
        await _send_email_callback()
        
    except Exception as e:
        print(f"Error in scheduled email task: {str(e)}")
        import traceback
        traceback.print_exc()


def start_scheduler(send_email_callback: Callable, interval_minutes: int = 60) -> bool:
    """
    Start the scheduler to send emails automatically every interval_minutes.
    
    Args:
        send_email_callback: Async function to call when it's time to send email
        interval_minutes: How often to send emails (default: 60 minutes / 1 hour)
        
    Returns:
        True if scheduler started successfully, False otherwise
    """
    global _scheduler, _send_email_callback
    
    if not APSCHEDULER_AVAILABLE:
        print("Warning: APScheduler not available. Install with: pip install apscheduler")
        return False
    
    if _scheduler is not None and _scheduler.running:
        print("Scheduler is already running")
        return True
    
    _send_email_callback = send_email_callback
    _scheduler = AsyncIOScheduler()
    
    # Schedule the task to run every interval_minutes
    _scheduler.add_job(
        _scheduled_email_task,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="send_options_email",
        name="Send Options Email",
        replace_existing=True
    )
    
    _scheduler.start()
    print(f"Scheduler started: will send emails every {interval_minutes} minutes")
    return True


def stop_scheduler() -> None:
    """
    Stop the scheduler if it's running.
    """
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
        print("Scheduler stopped")
        _scheduler = None


def is_scheduler_running() -> bool:
    """
    Check if the scheduler is currently running.
    
    Returns:
        True if scheduler is running, False otherwise
    """
    return _scheduler is not None and _scheduler.running

