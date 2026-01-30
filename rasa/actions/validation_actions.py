# =============================================================================
# VALIDATION ACTIONS
# =============================================================================
# Form validation actions for booking and meeting forms
# =============================================================================

import logging
import re
from typing import Any, Dict, List, Text, Optional
from datetime import datetime, timedelta

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict

from .utils.config_manager import ConfigManager
from .utils.validators import ValidationUtils

logger = logging.getLogger(__name__)


class ValidateBookingForm(FormValidationAction):
    """
    Validates slots in the booking form.
    """
    
    def name(self) -> Text:
        return "validate_booking_form"
    
    async def required_slots(
        self,
        domain_slots: List[Text],
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Text]:
        """
        Dynamically determine required slots based on task configuration.
        """
        # Get task config to determine required fields
        config_manager = ConfigManager()
        try:
            task_config = await config_manager.get_task_config("book_service")
            required_fields = task_config.get("required_fields", [])
            
            # Map config fields to slot names
            field_to_slot = {
                "service_type": "service_type",
                "date": "booking_date",
                "time": "booking_time",
                "name": "customer_name",
                "email": "customer_email",
                "phone": "customer_phone",
                "party_size": "party_size"
            }
            
            # Build required slots list
            slots = []
            for field in required_fields:
                if field in field_to_slot:
                    slots.append(field_to_slot[field])
            
            # Ensure minimum required slots
            minimum_slots = ["service_type", "booking_date", "booking_time", 
                          "customer_name", "customer_email"]
            for slot in minimum_slots:
                if slot not in slots:
                    slots.append(slot)
            
            return slots
            
        except Exception as e:
            logger.warning(f"Could not get task config, using defaults: {e}")
            return domain_slots
    
    async def validate_service_type(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate the service type against allowed services.
        """
        if not slot_value:
            return {"service_type": None}
        
        # Normalize the value
        service = slot_value.lower().strip()
        
        # Get allowed services from config
        config_manager = ConfigManager()
        try:
            task_config = await config_manager.get_task_config("book_service")
            allowed_services = task_config.get("services", [])
            
            # Check if service matches any allowed service
            for svc in allowed_services:
                svc_name = svc.get("name", "").lower() if isinstance(svc, dict) else svc.lower()
                svc_id = svc.get("id", "").lower() if isinstance(svc, dict) else svc.lower()
                
                # Check if enabled
                if isinstance(svc, dict) and not svc.get("enabled", True):
                    continue
                
                if service in [svc_name, svc_id] or svc_name in service:
                    return {"service_type": svc.get("name", svc) if isinstance(svc, dict) else svc}
            
            # Service not found
            services_list = [s.get("name", s) if isinstance(s, dict) else s 
                           for s in allowed_services 
                           if not isinstance(s, dict) or s.get("enabled", True)]
            
            dispatcher.utter_message(
                text=f"I'm sorry, '{slot_value}' isn't one of our available services. "
                     f"Please choose from: {', '.join(services_list)}"
            )
            return {"service_type": None}
            
        except Exception as e:
            logger.warning(f"Could not validate service type: {e}")
            # Allow any service if config unavailable
            return {"service_type": slot_value}
    
    async def validate_booking_date(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate booking date:
        - Must be a valid date
        - Must not be in the past
        - Must not be a blocked date
        - Must be within booking window
        """
        if not slot_value:
            return {"booking_date": None}
        
        # Parse the date
        parsed_date = ValidationUtils.parse_date(slot_value)
        
        if not parsed_date:
            dispatcher.utter_message(
                text="I couldn't understand that date. Please try formats like "
                     "'January 15', 'next Monday', or '01/15/2024'."
            )
            return {"booking_date": None}
        
        # Get config for validation
        config_manager = ConfigManager()
        try:
            task_config = await config_manager.get_task_config("book_service")
            blocked_dates = task_config.get("blocked_dates", [])
            booking_window = task_config.get("booking_window_days", 90)
            
            # Check if date is in the past
            today = datetime.now().date()
            if parsed_date < today:
                dispatcher.utter_message(
                    text="That date is in the past. Please choose a future date."
                )
                return {"booking_date": None}
            
            # Check booking window
            max_date = today + timedelta(days=booking_window)
            if parsed_date > max_date:
                dispatcher.utter_message(
                    text=f"We can only accept bookings up to {booking_window} days in advance. "
                         f"Please choose a date before {max_date.strftime('%B %d, %Y')}."
                )
                return {"booking_date": None}
            
            # Check blocked dates
            date_str = parsed_date.strftime("%Y-%m-%d")
            if date_str in blocked_dates:
                dispatcher.utter_message(
                    text=f"Sorry, we're not available on {parsed_date.strftime('%B %d, %Y')}. "
                         f"Please choose a different date."
                )
                return {"booking_date": None}
            
            # Valid date
            return {"booking_date": date_str}
            
        except Exception as e:
            logger.warning(f"Could not validate date against config: {e}")
            # Basic validation without config
            date_str = parsed_date.strftime("%Y-%m-%d")
            return {"booking_date": date_str}
    
    async def validate_booking_time(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate booking time against business hours.
        """
        if not slot_value:
            return {"booking_time": None}
        
        # Parse the time
        parsed_time = ValidationUtils.parse_time(slot_value)
        
        if not parsed_time:
            dispatcher.utter_message(
                text="I couldn't understand that time. Please try formats like "
                     "'2pm', '14:00', or '2:30 PM'."
            )
            return {"booking_time": None}
        
        # Get business hours from config
        config_manager = ConfigManager()
        try:
            task_config = await config_manager.get_task_config("book_service")
            business_hours = task_config.get("business_hours", {"start": "09:00", "end": "18:00"})
            
            start_hour = int(business_hours["start"].split(":")[0])
            end_hour = int(business_hours["end"].split(":")[0])
            
            if parsed_time.hour < start_hour or parsed_time.hour >= end_hour:
                dispatcher.utter_message(
                    text=f"That time is outside our business hours "
                         f"({business_hours['start']} - {business_hours['end']}). "
                         f"Please choose a time within these hours."
                )
                return {"booking_time": None}
            
            # Valid time
            time_str = parsed_time.strftime("%H:%M")
            return {"booking_time": time_str}
            
        except Exception as e:
            logger.warning(f"Could not validate time against config: {e}")
            time_str = parsed_time.strftime("%H:%M")
            return {"booking_time": time_str}
    
    async def validate_customer_email(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate email address format.
        """
        if not slot_value:
            return {"customer_email": None}
        
        # Clean the value
        email = slot_value.strip().lower()
        
        # Validate format
        if ValidationUtils.is_valid_email(email):
            return {"customer_email": email}
        else:
            dispatcher.utter_message(response="utter_email_invalid")
            return {"customer_email": None}
    
    async def validate_customer_phone(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate phone number format.
        """
        if not slot_value:
            return {"customer_phone": None}
        
        # Clean the value
        phone = ValidationUtils.clean_phone(slot_value)
        
        # Validate format
        if ValidationUtils.is_valid_phone(phone):
            return {"customer_phone": phone}
        else:
            dispatcher.utter_message(response="utter_phone_invalid")
            return {"customer_phone": None}
    
    async def validate_customer_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate customer name.
        """
        if not slot_value:
            return {"customer_name": None}
        
        name = slot_value.strip()
        
        # Basic validation - name should have at least 2 characters
        if len(name) < 2:
            dispatcher.utter_message(
                text="Please provide your full name."
            )
            return {"customer_name": None}
        
        return {"customer_name": name}


class ValidateMeetingForm(FormValidationAction):
    """
    Validates slots in the meeting scheduling form.
    """
    
    def name(self) -> Text:
        return "validate_meeting_form"
    
    async def validate_meeting_type(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate meeting type.
        """
        if not slot_value:
            return {"meeting_type": None}
        
        meeting_type = slot_value.strip().lower()
        
        # Get allowed meeting types from config
        config_manager = ConfigManager()
        try:
            task_config = await config_manager.get_task_config("schedule_meeting")
            allowed_types = task_config.get("meeting_types", [
                "sales call", "technical consultation", "general inquiry"
            ])
            
            # Fuzzy match
            for mt in allowed_types:
                if meeting_type in mt.lower() or mt.lower() in meeting_type:
                    return {"meeting_type": mt}
            
            dispatcher.utter_message(
                text=f"Please choose from: {', '.join(allowed_types)}"
            )
            return {"meeting_type": None}
            
        except Exception:
            return {"meeting_type": slot_value}
    
    async def validate_meeting_date(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate meeting date (similar to booking date).
        """
        if not slot_value:
            return {"meeting_date": None}
        
        parsed_date = ValidationUtils.parse_date(slot_value)
        
        if not parsed_date:
            dispatcher.utter_message(
                text="I couldn't understand that date. Please try again."
            )
            return {"meeting_date": None}
        
        # Check if in future
        if parsed_date <= datetime.now().date():
            dispatcher.utter_message(
                text="Please choose a future date for the meeting."
            )
            return {"meeting_date": None}
        
        return {"meeting_date": parsed_date.strftime("%Y-%m-%d")}
    
    async def validate_meeting_time(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate meeting time.
        """
        if not slot_value:
            return {"meeting_time": None}
        
        parsed_time = ValidationUtils.parse_time(slot_value)
        
        if not parsed_time:
            dispatcher.utter_message(
                text="I couldn't understand that time. Please try again."
            )
            return {"meeting_time": None}
        
        # Business hours check (9 AM - 5 PM for meetings)
        if parsed_time.hour < 9 or parsed_time.hour >= 17:
            dispatcher.utter_message(
                text="Meeting times are available between 9 AM and 5 PM."
            )
            return {"meeting_time": None}
        
        return {"meeting_time": parsed_time.strftime("%H:%M")}
    
    async def validate_meeting_duration(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate meeting duration.
        """
        if not slot_value:
            return {"meeting_duration": "30 minutes"}  # Default
        
        duration = slot_value.strip().lower()
        
        # Map common duration inputs
        duration_map = {
            "15": "15 minutes",
            "15 min": "15 minutes",
            "15 minutes": "15 minutes",
            "30": "30 minutes",
            "30 min": "30 minutes",
            "30 minutes": "30 minutes",
            "half hour": "30 minutes",
            "1 hour": "1 hour",
            "1hour": "1 hour",
            "60": "1 hour",
            "60 min": "1 hour",
            "one hour": "1 hour",
            "an hour": "1 hour"
        }
        
        normalized = duration_map.get(duration, duration)
        
        if normalized in ["15 minutes", "30 minutes", "1 hour"]:
            return {"meeting_duration": normalized}
        else:
            dispatcher.utter_message(
                text="Please choose a duration: 15 minutes, 30 minutes, or 1 hour."
            )
            return {"meeting_duration": None}
    
    async def validate_attendee_email(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate attendee email.
        """
        if not slot_value:
            return {"attendee_email": None}
        
        email = slot_value.strip().lower()
        
        if ValidationUtils.is_valid_email(email):
            return {"attendee_email": email}
        else:
            dispatcher.utter_message(response="utter_email_invalid")
            return {"attendee_email": None}


class ValidateBookingLookupForm(FormValidationAction):
    """
    Validates the booking lookup form.
    """
    
    def name(self) -> Text:
        return "validate_booking_lookup_form"
    
    async def validate_booking_id(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> Dict[Text, Any]:
        """
        Validate booking reference ID format.
        """
        if not slot_value:
            return {"booking_id": None}
        
        booking_id = slot_value.strip().upper()
        
        # Expected format: BK-XXXX-XXXX or similar
        pattern = r'^BK-?\d{4}-?\d{4}$|^BK\d{8}$'
        
        if re.match(pattern, booking_id):
            # Normalize format
            booking_id = booking_id.replace("BK", "BK-").replace("--", "-")
            if not "-" in booking_id[3:]:
                booking_id = f"{booking_id[:7]}-{booking_id[7:]}"
            return {"booking_id": booking_id}
        else:
            dispatcher.utter_message(
                text="That doesn't look like a valid booking reference. "
                     "It should be in the format BK-XXXX-XXXX."
            )
            return {"booking_id": None}
