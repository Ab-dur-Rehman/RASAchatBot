# =============================================================================
# VALIDATION UTILITIES
# =============================================================================
# Common validation functions for user input
# =============================================================================

import re
import logging
from typing import Any, Dict, Optional, Union
from datetime import datetime, date, timedelta
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


class ValidationUtils:
    """
    Utility class for validating and parsing user input.
    """
    
    # =========================================================================
    # EMAIL VALIDATION
    # =========================================================================
    
    @staticmethod
    def is_valid_email(email: str) -> bool:
        """
        Validate email address format.
        
        Args:
            email: Email address to validate
        
        Returns:
            True if valid email format
        """
        if not email:
            return False
        
        # RFC 5322 compliant regex (simplified)
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))
    
    # =========================================================================
    # PHONE VALIDATION
    # =========================================================================
    
    @staticmethod
    def is_valid_phone(phone: str) -> bool:
        """
        Validate phone number format.
        
        Args:
            phone: Phone number to validate
        
        Returns:
            True if valid phone format
        """
        if not phone:
            return False
        
        # Remove common formatting characters
        cleaned = re.sub(r'[\s\-\(\)\.\+]', '', phone)
        
        # Check if remaining chars are digits and reasonable length
        if not cleaned.isdigit():
            return False
        
        return 7 <= len(cleaned) <= 15
    
    @staticmethod
    def clean_phone(phone: str) -> str:
        """
        Clean and normalize phone number.
        
        Args:
            phone: Raw phone number input
        
        Returns:
            Cleaned phone number
        """
        if not phone:
            return ""
        
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Format as (XXX) XXX-XXXX for US numbers
        if len(cleaned) == 10:
            return f"({cleaned[:3]}) {cleaned[3:6]}-{cleaned[6:]}"
        elif len(cleaned) == 11 and cleaned.startswith('1'):
            return f"+1 ({cleaned[1:4]}) {cleaned[4:7]}-{cleaned[7:]}"
        
        return cleaned
    
    # =========================================================================
    # DATE PARSING
    # =========================================================================
    
    @staticmethod
    def parse_date(date_input: Union[str, dict]) -> Optional[date]:
        """
        Parse various date formats into a date object.
        
        Handles:
        - ISO format: "2024-01-15"
        - Natural language: "next Monday", "tomorrow"
        - Duckling output: {"value": "2024-01-15T00:00:00.000-07:00", ...}
        
        Args:
            date_input: Date string or Duckling entity dict
        
        Returns:
            Parsed date object or None if parsing fails
        """
        if not date_input:
            return None
        
        try:
            # Handle Duckling output (dict with 'value' key)
            if isinstance(date_input, dict):
                value = date_input.get("value")
                if value:
                    date_input = value
                else:
                    return None
            
            # Try ISO format first
            if isinstance(date_input, str):
                # Remove time component if present
                if 'T' in date_input:
                    date_input = date_input.split('T')[0]
                
                # Try various parsing methods
                try:
                    parsed = date_parser.parse(date_input, fuzzy=True)
                    return parsed.date()
                except (ValueError, TypeError):
                    pass
                
                # Handle relative dates
                today = datetime.now().date()
                lower_input = date_input.lower().strip()
                
                if lower_input == "today":
                    return today
                elif lower_input == "tomorrow":
                    return today + timedelta(days=1)
                elif lower_input == "yesterday":
                    return today - timedelta(days=1)
                elif "next" in lower_input:
                    return ValidationUtils._parse_next_day(lower_input, today)
                elif "this" in lower_input:
                    return ValidationUtils._parse_this_day(lower_input, today)
            
            return None
            
        except Exception as e:
            logger.warning(f"Date parsing error for '{date_input}': {e}")
            return None
    
    @staticmethod
    def _parse_next_day(text: str, today: date) -> Optional[date]:
        """Parse 'next Monday', 'next week', etc."""
        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        
        text_lower = text.lower()
        
        # Check for weekday
        for day_name, day_num in weekdays.items():
            if day_name in text_lower:
                days_ahead = day_num - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)
        
        # "next week" = next Monday
        if "week" in text_lower:
            days_ahead = 7 - today.weekday()
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
        
        return None
    
    @staticmethod
    def _parse_this_day(text: str, today: date) -> Optional[date]:
        """Parse 'this Monday', 'this week', etc."""
        weekdays = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        
        text_lower = text.lower()
        
        for day_name, day_num in weekdays.items():
            if day_name in text_lower:
                days_diff = day_num - today.weekday()
                if days_diff < 0:
                    days_diff += 7
                return today + timedelta(days=days_diff)
        
        return None
    
    # =========================================================================
    # TIME PARSING
    # =========================================================================
    
    @staticmethod
    def parse_time(time_input: Union[str, dict]) -> Optional[datetime]:
        """
        Parse various time formats into a datetime object (date = today).
        
        Handles:
        - 24-hour: "14:00", "14:30"
        - 12-hour: "2pm", "2:30 PM", "2 o'clock"
        - Duckling output
        
        Args:
            time_input: Time string or Duckling entity dict
        
        Returns:
            Datetime object with parsed time or None
        """
        if not time_input:
            return None
        
        try:
            # Handle Duckling output
            if isinstance(time_input, dict):
                value = time_input.get("value")
                if value:
                    time_input = value
                else:
                    return None
            
            if isinstance(time_input, str):
                # If it contains a date component, extract time
                if 'T' in time_input:
                    time_input = time_input.split('T')[1].split('.')[0].split('-')[0].split('+')[0]
                
                # Clean up the input
                time_str = time_input.strip().lower()
                
                # Try direct parsing
                try:
                    parsed = date_parser.parse(time_str)
                    return parsed
                except (ValueError, TypeError):
                    pass
                
                # Handle common patterns
                # "2pm" / "2 pm" / "2PM"
                match = re.match(r'^(\d{1,2})\s*(am|pm)?$', time_str, re.IGNORECASE)
                if match:
                    hour = int(match.group(1))
                    period = match.group(2)
                    
                    if period:
                        if period.lower() == 'pm' and hour != 12:
                            hour += 12
                        elif period.lower() == 'am' and hour == 12:
                            hour = 0
                    
                    return datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
                
                # "2:30pm" / "2:30 pm"
                match = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)?$', time_str, re.IGNORECASE)
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    period = match.group(3)
                    
                    if period:
                        if period.lower() == 'pm' and hour != 12:
                            hour += 12
                        elif period.lower() == 'am' and hour == 12:
                            hour = 0
                    
                    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # "14:00" (24-hour)
                match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            return None
            
        except Exception as e:
            logger.warning(f"Time parsing error for '{time_input}': {e}")
            return None
    
    # =========================================================================
    # DATE/TIME VALIDATION
    # =========================================================================
    
    @staticmethod
    def validate_datetime(
        date_str: str,
        time_str: str,
        business_hours: Dict[str, str],
        blocked_dates: list
    ) -> Dict[str, Any]:
        """
        Validate a date/time combination against business rules.
        
        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format
            business_hours: Dict with 'start' and 'end' times
            blocked_dates: List of blocked dates
        
        Returns:
            Dict with 'valid' bool and 'message' string
        """
        result = {"valid": True, "message": ""}
        
        try:
            # Parse date
            booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            
            # Check if in past
            if booking_date < today:
                return {"valid": False, "message": "Cannot book dates in the past"}
            
            # Check blocked dates
            if date_str in blocked_dates:
                return {"valid": False, "message": f"{date_str} is not available for booking"}
            
            # Check time within business hours
            booking_time = datetime.strptime(time_str, "%H:%M").time()
            start_time = datetime.strptime(business_hours.get("start", "09:00"), "%H:%M").time()
            end_time = datetime.strptime(business_hours.get("end", "18:00"), "%H:%M").time()
            
            if booking_time < start_time or booking_time >= end_time:
                return {
                    "valid": False,
                    "message": f"Time must be between {business_hours['start']} and {business_hours['end']}"
                }
            
            return result
            
        except (ValueError, TypeError) as e:
            return {"valid": False, "message": f"Invalid date/time format: {str(e)}"}
    
    # =========================================================================
    # BOOKING ID VALIDATION
    # =========================================================================
    
    @staticmethod
    def is_valid_booking_id(booking_id: str) -> bool:
        """
        Validate booking reference ID format.
        
        Expected format: BK-XXXX-XXXX where X is a digit
        
        Args:
            booking_id: Booking reference to validate
        
        Returns:
            True if valid format
        """
        if not booking_id:
            return False
        
        pattern = r'^BK-?\d{4}-?\d{4}$'
        return bool(re.match(pattern, booking_id.upper()))
