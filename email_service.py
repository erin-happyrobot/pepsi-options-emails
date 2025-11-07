import os
import json
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config


def format_timestamp(timestamp: Any) -> str:
    """
    Format a timestamp (datetime object or ISO string) to a readable string in Central time.
    
    Args:
        timestamp: Can be a datetime object, ISO string, or None (assumed to be in UTC)
        
    Returns:
        Formatted timestamp string in Central time or 'N/A' if invalid
    """
    if timestamp is None:
        return 'N/A'
    
    try:
        # If it's already a datetime object
        if isinstance(timestamp, datetime):
            dt = timestamp
        # If it's a string, parse it
        elif isinstance(timestamp, str):
            # Handle ISO format strings (with or without 'Z')
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            return 'N/A'
        
        # Ensure datetime is timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        # Convert to Central time
        central_tz = ZoneInfo("America/Chicago")
        dt_central = dt.astimezone(central_tz)
        
        # Format as readable date/time in Central time
        return dt_central.strftime('%Y-%m-%d %H:%M:%S Central')
    except (ValueError, AttributeError) as e:
        print(f"Error formatting timestamp {timestamp}: {e}")
        return 'N/A'


def get_timestamp_for_sort(option: Dict[str, Any]) -> datetime:
    """
    Extract and parse created_at timestamp from an option for sorting purposes.
    
    Args:
        option: Option dictionary
        
    Returns:
        datetime object (UTC) for sorting, or datetime.min if invalid/missing
    """
    created_at_raw = option.get('created_at')
    if created_at_raw is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        if isinstance(created_at_raw, datetime):
            dt = created_at_raw
        elif isinstance(created_at_raw, str):
            dt = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00'))
        else:
            return datetime.min.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def format_phone_number(phone: Any) -> str:
    """
    Format a phone number to a readable format: (XXX) XXX-XXXX.
    
    Args:
        phone: Phone number as string, number, or None
        
    Returns:
        Formatted phone number string or 'N/A' if invalid
    """
    if phone is None:
        return 'N/A'
    
    # Convert to string and remove all non-digit characters
    phone_str = str(phone).strip()
    if not phone_str or phone_str == 'N/A':
        return 'N/A'
    
    # Extract only digits
    digits = ''.join(filter(str.isdigit, phone_str))
    
    # Handle different cases
    if len(digits) == 10:
        # Standard 10-digit US number: (925) 989-8099
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
    elif len(digits) == 11 and digits[0] == '1':
        # 11-digit number starting with 1 (US country code): remove leading 1
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:11]}"
    elif len(digits) > 0:
        # If it doesn't match standard formats, return cleaned version
        # but try to format if it's close
        if len(digits) >= 10:
            return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"
        else:
            # Return as-is if too short
            return phone_str
    else:
        return 'N/A'


def format_options_email(options: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Format options data into an HTML email, grouped by load.
    
    Args:
        options: List of option records with associated load data
        
    Returns:
        Tuple of (subject, html_body)
    """
    count = len(options)
    subject = f"Options Report - {count} Option{'s' if count != 1 else ''} Available"
    
    html_body = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .header {{
                background-color: #0066cc;
                color: white;
                padding: 20px;
                text-align: center;
            }}
            .content {{
                padding: 20px;
            }}
            .load-section {{
                margin-bottom: 30px;
                border: 1px solid #ddd;
                border-radius: 5px;
                overflow: hidden;
            }}
            .load-header {{
                background-color: #0066cc;
                color: white;
                padding: 15px 20px;
                font-size: 18px;
                font-weight: bold;
            }}
            .load-lane {{
                background-color: #f0f0f0;
                padding: 10px 20px;
                font-size: 14px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #0066cc;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            .summary {{
                background-color: #e6f3ff;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Options Report</h1>
            <p>Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </div>
        <div class="content">
            <div class="summary">
                <h2>Summary</h2>
                <p><strong>Total Options:</strong> {count}</p>
            </div>
    """
    
    if count > 0:
        # Group options by load (custom_load_id)
        loads_dict = defaultdict(list)
        
        for option in options:
            load = option.get('loads', {})
            if isinstance(load, dict):
                custom_load_id = load.get('custom_load_id', 'Unknown')
                loads_dict[custom_load_id].append(option)
        
        # Generate HTML for each load group
        for custom_load_id, load_options in loads_dict.items():
            # Sort options by created_at descending (most recent first)
            load_options.sort(key=get_timestamp_for_sort, reverse=True)
            
            # Get load info from first option (all options for same load have same load data)
            first_option = load_options[0]
            load = first_option.get('loads', {})
            origin = load.get('origin', 'N/A') if isinstance(load, dict) else 'N/A'
            destination = load.get('destination', 'N/A') if isinstance(load, dict) else 'N/A'
            
            # Build lane string
            lane = f"{origin} → {destination}" if origin != 'N/A' and destination != 'N/A' else 'N/A'
            
            html_body += f"""
            <div class="load-section">
                <div class="load-header">
                    Load Number: {custom_load_id}
                </div>
                <div class="load-lane">
                    Lane: {lane}
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Carrier MC</th>
                            <th>Carrier DOT</th>
                            <th>Offer Amount</th>
                            <th>Phone Number</th>
                            <th>Option Logged Time</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for option in load_options:
                carrier_mc = option.get('carrier_mc', 'N/A') or 'N/A'
                carrier_dot = option.get('carrier_dot', 'N/A') or 'N/A'
                offered_rate = option.get('offered_rate', 'N/A')
                phone_number_raw = option.get('phone_number', 'N/A') or 'N/A'
                phone_number = format_phone_number(phone_number_raw)
                created_at_raw = option.get('created_at')
                option_logged_time = format_timestamp(created_at_raw)
                
                # Format rate
                rate_display = f"${offered_rate:.2f}" if isinstance(offered_rate, (int, float)) else str(offered_rate)
                
                html_body += f"""
                        <tr>
                            <td>{carrier_mc}</td>
                            <td>{carrier_dot}</td>
                            <td>{rate_display}</td>
                            <td>{phone_number}</td>
                            <td>{option_logged_time}</td>
                        </tr>
                """
            
            html_body += """
                    </tbody>
                </table>
            </div>
            """
        
    else:
        html_body += """
            <p><strong>No options found matching the criteria.</strong></p>
        """
    
    html_body += """
        </div>
    </body>
    </html>
    """
    
    return subject, html_body


def format_options_email_text(options: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Format options data into a plain text email, grouped by load.
    
    Args:
        options: List of option records with associated load data
        
    Returns:
        Tuple of (subject, text_body)
    """
    count = len(options)
    subject = f"Options Report - {count} Option{'s' if count != 1 else ''} Available"
    
    text_body = f"""OPTIONS REPORT
Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

SUMMARY
Total Options: {count}

"""
    
    if count > 0:
        # Group options by load (custom_load_id)
        loads_dict = defaultdict(list)
        
        for option in options:
            load = option.get('loads', {})
            if isinstance(load, dict):
                custom_load_id = load.get('custom_load_id', 'Unknown')
                loads_dict[custom_load_id].append(option)
        
        # Generate text for each load group
        for custom_load_id, load_options in loads_dict.items():
            # Sort options by created_at descending (most recent first)
            load_options.sort(key=get_timestamp_for_sort, reverse=True)
            
            # Get load info from first option (all options for same load have same load data)
            first_option = load_options[0]
            load = first_option.get('loads', {})
            origin = load.get('origin', 'N/A') if isinstance(load, dict) else 'N/A'
            destination = load.get('destination', 'N/A') if isinstance(load, dict) else 'N/A'
            
            # Build lane string
            lane = f"{origin} → {destination}" if origin != 'N/A' and destination != 'N/A' else 'N/A'
            
            text_body += f"""
{'='*60}
LOAD NUMBER: {custom_load_id}
LANE: {lane}
{'='*60}

Carrier MC        Carrier DOT      Offer Amount     Phone Number      Option Logged Time
{'─'*80}
"""
            
            for option in load_options:
                carrier_mc = option.get('carrier_mc', 'N/A') or 'N/A'
                carrier_dot = option.get('carrier_dot', 'N/A') or 'N/A'
                offered_rate = option.get('offered_rate', 'N/A')
                phone_number_raw = option.get('phone_number', 'N/A') or 'N/A'
                phone_number = format_phone_number(phone_number_raw)
                created_at_raw = option.get('created_at')
                option_logged_time = format_timestamp(created_at_raw)
                
                # Format rate
                rate_display = f"${offered_rate:.2f}" if isinstance(offered_rate, (int, float)) else str(offered_rate)
                
                # Format with fixed-width columns
                text_body += f"{carrier_mc:<16} {carrier_dot:<16} {rate_display:<16} {phone_number:<20} {option_logged_time}\n"
            
            text_body += "\n"
        
    else:
        text_body += "No options found matching the criteria.\n"
    
    return subject, text_body


def invoke_lambda(payload: dict) -> dict:
    """
    Invoke an AWS Lambda function with the given payload.
    
    Args:
        payload: Dictionary payload to send to Lambda function
        
    Returns:
        Dictionary response from Lambda function
        
    Raises:
        NoCredentialsError: If AWS credentials are not set
        ClientError: If Lambda invocation fails
    """
    try:
        # Disable client-side retries to avoid duplicate invokes
        client = boto3.client(
            "lambda",
            region_name=os.environ.get("AWS_REGION", "us-east-2"),
            config=Config(
                retries={"max_attempts": 0, "mode": "standard"}, 
                connect_timeout=3, 
                read_timeout=10
            ),
        )
        
        lambda_function_name = os.environ.get("LAMBDA_FUNCTION_NAME")
        if not lambda_function_name:
            raise ValueError("LAMBDA_FUNCTION_NAME environment variable is not set")
        
        resp = client.invoke(
            FunctionName=lambda_function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        
        status_code = resp.get("StatusCode")
        function_error = resp.get("FunctionError")
        
        print(f"Lambda invoke StatusCode={status_code} FunctionError={function_error}")
        
        # Read the payload
        payload_data = resp["Payload"].read().decode("utf-8")
        
        # If Lambda function errored, the payload contains error details
        if function_error:
            error_data = json.loads(payload_data) if payload_data else {}
            error_message = error_data.get("errorMessage", "Unknown Lambda error")
            error_type = error_data.get("errorType", "UnknownError")
            raise RuntimeError(f"Lambda function error ({error_type}): {error_message}")
        
        # Try to parse the response
        try:
            return json.loads(payload_data)
        except json.JSONDecodeError:
            # If it's not JSON, return the raw response
            return {"raw_response": payload_data}
            
    except NoCredentialsError:
        raise ValueError("Missing AWS credentials. Set AWS_ACCESS_KEY_ID/SECRET (and SESSION_TOKEN if temp) and AWS_REGION.")
    except ClientError as e:
        raise RuntimeError(f"Error invoking Lambda: {e}")


def send_options_email(
    options: List[Dict[str, Any]], 
    recipient: Optional[Union[str, List[str]]] = None,
    sender: Optional[str] = None,
    org_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an email with options data by invoking a Lambda function.
    
    Args:
        options: List of option records
        recipient: Email recipient(s) - can be:
            - Single email as string: "user@example.com"
            - Multiple emails as comma-separated string: "user1@example.com, user2@example.com"
            - List of emails: ["user1@example.com", "user2@example.com"]
            - Defaults to EMAIL_TO env var (supports comma-separated)
        sender: Email sender (defaults to SENDER_EMAIL env var)
        org_id: Organization ID (required by Lambda function)
        
    Returns:
        Dictionary with success status and message/error
    """
    try:
        recipient_email = recipient or os.environ.get("EMAIL_TO")
        sender_email = sender or os.environ.get("SENDER_EMAIL")
        org_id_value = org_id or os.environ.get("ORG_ID")
        
        if not recipient_email:
            raise ValueError("EMAIL_TO environment variable is not set")
        if not sender_email:
            raise ValueError("SENDER_EMAIL environment variable is not set")
        if not org_id_value:
            raise ValueError("org_id must be provided (either as parameter or ORG_ID env var)")
        
        # Parse recipient_email: support comma-separated emails or list
        if isinstance(recipient_email, str):
            # Split by comma and strip whitespace, remove empty strings
            recipient_list = [email.strip() for email in recipient_email.split(",") if email.strip()]
        elif isinstance(recipient_email, list):
            # Already a list, use as-is
            recipient_list = recipient_email
        else:
            # Fallback: wrap in list
            recipient_list = [str(recipient_email)]
        
        if not recipient_list:
            raise ValueError("No valid email recipients found")
        
        subject, text_body = format_options_email_text(options)
        
        # Prepare payload for Lambda function
        # The Lambda function expects: orgId (camelCase), to (array), body, from, subject
        payload = {
            "orgId": org_id_value,
            "to": recipient_list,
            "from": sender_email,
            "subject": subject,
            "body": text_body
        }
        
        # Invoke Lambda function to send email
        lambda_response = invoke_lambda(payload)
        
        # Lambda function should return a response with success/error
        # Adjust based on your Lambda function's response format
        if isinstance(lambda_response, dict):
            # Check for common success indicators
            # 200 = OK, 202 = Accepted (common for async/queued operations)
            status_code = lambda_response.get("statusCode")
            if (lambda_response.get("success") is True or 
                status_code in (200, 202) or
                lambda_response.get("status") == "success"):
                return {
                    "success": True,
                    "message": f"Email queued/sent successfully to {', '.join(recipient_list)}",
                    "lambda_response": lambda_response
                }
            else:
                # Extract error message from various possible formats
                error_msg = (
                    lambda_response.get("error") or 
                    lambda_response.get("errorMessage") or 
                    lambda_response.get("message") or
                    f"Lambda returned unsuccessful response: {json.dumps(lambda_response)}"
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "lambda_response": lambda_response
                }
        else:
            # Lambda returned something unexpected, assume success if no exception
            return {
                "success": True,
                "message": f"Email sent successfully to {', '.join(recipient_list)}",
                "lambda_response": lambda_response
            }
            
    except ValueError as ve:
        print(f"Configuration error: {str(ve)}")
        return {
            "success": False,
            "error": str(ve)
        }
    except Exception as e:
        print(f"Error sending email via Lambda: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

