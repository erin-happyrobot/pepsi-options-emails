import os
from typing import List, Dict, Any, Union
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from supabase import create_client, Client


def get_supabase() -> Client:
    """
    Initialize and return Supabase client using environment variables.
    
    Returns:
        Supabase Client instance
        
    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY environment variables are not set
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url:
        raise ValueError("SUPABASE_URL environment variable is not set")
    if not key:
        raise ValueError("SUPABASE_KEY environment variable is not set")
    
    return create_client(url, key)


def is_prebook_load(pickup_date_close: Union[str, datetime, None], origin_state: str | None = None) -> bool:
    """
    Determine if a load is considered pre-book.
    
    A load is considered pre-book if:
    1. The pickup date is in the future (not in the past)
    2. The pickup does not occur today (Central time)
    3. AND if it is not tomorrow before 9:00 AM Central when the current time is after noon Central
    
    Args:
        pickup_date_close: The pickup date close timestamp (ISO format string)
        origin_state: The origin state (not currently used, but kept for future timezone mapping)
        
    Returns:
        True if the load is pre-book, False otherwise
    """
    try:
        # Parse pickup date (assuming it's in UTC or ISO format)
        if pickup_date_close is None:
            return False
            
        # Parse the pickup date - handle both datetime objects and strings
        if isinstance(pickup_date_close, str):
            pickup_dt = datetime.fromisoformat(pickup_date_close.replace('Z', '+00:00'))
        else:
            pickup_dt = pickup_date_close
        
        # Ensure pickup_dt is timezone-aware
        if pickup_dt.tzinfo is None:
            pickup_dt = pickup_dt.replace(tzinfo=timezone.utc)
        
        # Convert to Central time
        central_tz = ZoneInfo("America/Chicago")
        pickup_central = pickup_dt.astimezone(central_tz)
        
        # Get current time in Central timezone
        now_central = datetime.now(central_tz)
        
        # Get dates (without time) for comparison
        pickup_date = pickup_central.date()
        today = now_central.date()
        tomorrow = today + timedelta(days=1)
        
        # Check if pickup is in the past - NOT prebook
        if pickup_date < today:
            return False
        
        # Check if pickup is today - NOT prebook
        if pickup_date == today:
            return False
        
        # Check if current time is after noon Central AND pickup is tomorrow before 9:00 AM Central - NOT prebook
        if pickup_date == tomorrow:
            if now_central.hour >= 12:  # Current time is after noon Central
                if pickup_central.hour < 9:  # Pickup is before 9:00 AM Central
                    return False
        
        # Otherwise, it's prebook (pickup is in the future)
        return True
        
    except Exception as e:
        print(f"Error checking prebook status for pickup_date_close={pickup_date_close}: {e}")
        # On error, default to False (not prebook) to be safe
        return False


def get_options_with_available_loads(org_id: str) -> List[Dict[str, Any]]:
    """
    Query ALL options for loads where:
    - Load status is 'available'
    - Load is pre-book (pickup not today, and not tomorrow before 9 AM if current time is after noon)
    - org_id matches
    
    Returns all options for each matching load, regardless of option status.
    
    Args:
        org_id: The organization ID to filter by
        
    Returns:
        List of ALL option records (all statuses) with their associated load data
        for loads that have status='available' and are pre-book
        
    Raises:
        Exception: If the Supabase query fails
    """
    supabase = get_supabase()
    
    try:
        # First, get loads that match our criteria (status='available' and org_id)
        loads_result = (
            supabase.table("loads")
            .select("id, status, org_id, custom_load_id, pickup_date_close, origin_location_id, destination_location_id")
            .eq("status", "available")
            .eq("org_id", org_id)
            .execute()
        )
        
        if not loads_result.data or len(loads_result.data) == 0:
            return []
        
        # Get origin location IDs for timezone lookup
        origin_location_ids = [load["origin_location_id"] for load in loads_result.data if load.get("origin_location_id")]
        dest_location_ids = [load["destination_location_id"] for load in loads_result.data if load.get("destination_location_id")]
        all_location_ids = list(set(origin_location_ids + dest_location_ids))
        
        # Query locations separately to get state information
        locations_map = {}
        if all_location_ids:
            locations_result = (
                supabase.table("locations")
                .select("id, city, state")
                .in_("id", all_location_ids)
                .execute()
            )
            
            if locations_result.data:
                locations_map = {loc["id"]: loc for loc in locations_result.data}
        else:
            # Debug: if no location IDs found, the loads might not have location references
            print(f"Warning: No location IDs found in loads. Origin IDs: {len(origin_location_ids)}, Dest IDs: {len(dest_location_ids)}")
        
        # Filter loads to only include pre-book loads
        prebook_loads = []
        for load in loads_result.data:
            pickup_date_close = load.get("pickup_date_close")
            origin_location_id = load.get("origin_location_id")
            
            # Get origin state for timezone (if needed in future)
            origin_state = None
            if origin_location_id and origin_location_id in locations_map:
                origin_state = locations_map[origin_location_id].get("state")
            
            # Check if load is pre-book
            if is_prebook_load(pickup_date_close, origin_state):
                prebook_loads.append(load)
        
        if not prebook_loads:
            return []
        
        # Get load IDs for pre-book loads only
        load_ids = [load["id"] for load in prebook_loads]
        
        # Create a map of load_id to load data for quick lookup
        loads_map = {load["id"]: load for load in prebook_loads}
        
        # Query ALL options for these loads (no status filter on options)
        # This gets every option for each available load
        options_result = (
            supabase.table("options")
            .select("*")
            .in_("load_id", load_ids)
            # No .eq("status", ...) filter - get ALL options regardless of status
            .execute()
        )
        
        if not options_result.data:
            return []
        
        # Get carrier IDs from options
        carrier_ids = [opt.get("carrier_id") for opt in options_result.data if opt.get("carrier_id")]
        
        # Query carriers separately
        carriers_map = {}
        if carrier_ids:
            carriers_result = (
                supabase.table("carriers")
                .select("id, name, mc_number, dot_number")
                .in_("id", carrier_ids)
                .execute()
            )
            
            if carriers_result.data:
                carriers_map = {carrier["id"]: carrier for carrier in carriers_result.data}
        
        # Attach enriched load data and carrier info to each option
        options_list = []
        for option in options_result.data:
            load_id = option.get("load_id")
            if load_id in loads_map:
                load = loads_map[load_id]
                
                # Build origin string from locations_map
                origin = None
                origin_location_id = load.get("origin_location_id")
                if origin_location_id:
                    if origin_location_id in locations_map:
                        origin_loc = locations_map[origin_location_id]
                        origin_city = origin_loc.get("city", "")
                        origin_state = origin_loc.get("state", "")
                        origin = f"{origin_city}, {origin_state}".strip(", ")
                    else:
                        # Location ID exists but not found in map - might be missing from locations table
                        origin = f"Location ID: {origin_location_id} (not found)"
                
                # Build destination string from locations_map
                destination = None
                dest_location_id = load.get("destination_location_id")
                if dest_location_id:
                    if dest_location_id in locations_map:
                        dest_loc = locations_map[dest_location_id]
                        dest_city = dest_loc.get("city", "")
                        dest_state = dest_loc.get("state", "")
                        destination = f"{dest_city}, {dest_state}".strip(", ")
                    else:
                        # Location ID exists but not found in map - might be missing from locations table
                        destination = f"Location ID: {dest_location_id} (not found)"
                
                # Get carrier info from carriers_map
                carrier_id = option.get("carrier_id")
                carrier_name = None
                carrier_mc = None
                carrier_dot = None
                if carrier_id and carrier_id in carriers_map:
                    carrier = carriers_map[carrier_id]
                    carrier_name = carrier.get("name")
                    carrier_mc = carrier.get("mc_number")
                    carrier_dot = carrier.get("dot_number")
                
                # Get phone number from options table (phone field) - not from carrier_contacts
                # The phone field is directly on the options table
                phone_number = option.get("phone")
                
                # Attach enriched load data to each option
                option["loads"] = {
                    "id": load.get("id"),
                    "status": load.get("status"),
                    "org_id": load.get("org_id"),
                    "custom_load_id": load.get("custom_load_id"),
                    "pickup_date_close": load.get("pickup_date_close"),
                    "origin": origin,
                    "destination": destination
                }
                
                # Attach carrier info directly to option for easier access
                option["carrier_name"] = carrier_name
                option["carrier_mc"] = carrier_mc
                option["carrier_dot"] = carrier_dot
                option["phone_number"] = phone_number
                
                options_list.append(option)
        
        return options_list
    except Exception as e:
        print(f"Error querying options with available loads: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


