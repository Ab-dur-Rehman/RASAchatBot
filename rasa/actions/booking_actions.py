# =============================================================================
# BOOKING ACTIONS
# =============================================================================
# Custom actions for booking management: create, cancel, reschedule, status check
# =============================================================================

import logging
import hashlib
from typing import Any, Dict, List, Text, Optional
from datetime import datetime, timedelta

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction

from .utils.api_client import BackendAPIClient
from .utils.config_manager import ConfigManager
from .utils.validators import ValidationUtils
from .utils.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class ActionCreateBooking(Action):
    """
    Creates a new booking via the backend API.
    
    Required slots:
    - service_type
    - booking_date
    - booking_time
    - customer_name
    - customer_email
    - customer_phone
    """
    
    def name(self) -> Text:
        return "action_create_booking"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Extract slot values
        service_type = tracker.get_slot("service_type")
        booking_date = tracker.get_slot("booking_date")
        booking_time = tracker.get_slot("booking_time")
        customer_name = tracker.get_slot("customer_name")
        customer_email = tracker.get_slot("customer_email")
        customer_phone = tracker.get_slot("customer_phone")
        party_size = tracker.get_slot("party_size") or 1
        
        # Validate all required fields are present
        if not all([service_type, booking_date, booking_time, customer_name, customer_email]):
            dispatcher.utter_message(
                text="I'm missing some information needed for your booking. Let me help you fill in the details."
            )
            return [FollowupAction("booking_form")]
        
        try:
            # Initialize API client
            api_client = BackendAPIClient()
            
            # Prepare booking payload
            booking_payload = {
                "service_type": service_type,
                "date": booking_date,
                "time": booking_time,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "phone": customer_phone
                },
                "party_size": int(party_size),
                "source": "chatbot",
                "conversation_id": tracker.sender_id
            }
            
            # Call backend API with retry logic
            response = await api_client.create_booking(booking_payload)
            
            if response.get("success"):
                booking_id = response.get("booking_id")
                
                # Log successful booking (PII-safe)
                await AuditLogger.log_action(
                    action="create_booking",
                    booking_id=booking_id,
                    conversation_id=tracker.sender_id,
                    data_hash=hashlib.sha256(customer_email.encode()).hexdigest()[:16],
                    status="success"
                )
                
                # Return success with booking reference
                return [
                    SlotSet("current_booking", response),
                    SlotSet("booking_id", booking_id)
                ]
            else:
                # Handle API error response
                error_message = response.get("error", "Unknown error occurred")
                logger.error(f"Booking creation failed: {error_message}")
                
                await AuditLogger.log_action(
                    action="create_booking",
                    conversation_id=tracker.sender_id,
                    status="failed",
                    error=error_message
                )
                
                dispatcher.utter_message(response="utter_booking_error")
                return []
                
        except Exception as e:
            logger.exception(f"Exception during booking creation: {str(e)}")
            dispatcher.utter_message(response="utter_booking_error")
            
            await AuditLogger.log_action(
                action="create_booking",
                conversation_id=tracker.sender_id,
                status="exception",
                error=str(e)
            )
            
            return []


class ActionCancelBooking(Action):
    """
    Cancels an existing booking via the backend API.
    
    Required slots:
    - booking_id
    """
    
    def name(self) -> Text:
        return "action_cancel_booking"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        booking_id = tracker.get_slot("booking_id")
        
        if not booking_id:
            dispatcher.utter_message(
                text="I need your booking reference number to cancel. It looks like BK-XXXX-XXXX."
            )
            return [FollowupAction("booking_lookup_form")]
        
        try:
            api_client = BackendAPIClient()
            
            # Call cancel endpoint
            response = await api_client.cancel_booking(booking_id)
            
            if response.get("success"):
                await AuditLogger.log_action(
                    action="cancel_booking",
                    booking_id=booking_id,
                    conversation_id=tracker.sender_id,
                    status="success"
                )
                
                return [
                    SlotSet("current_booking", None),
                    SlotSet("booking_id", booking_id)
                ]
            else:
                error = response.get("error", "Unable to cancel booking")
                
                if "not found" in error.lower():
                    dispatcher.utter_message(
                        text=f"I couldn't find a booking with reference {booking_id}. Please check the number and try again."
                    )
                else:
                    dispatcher.utter_message(
                        text=f"I wasn't able to cancel that booking: {error}"
                    )
                
                return []
                
        except Exception as e:
            logger.exception(f"Exception during booking cancellation: {str(e)}")
            dispatcher.utter_message(response="utter_booking_error")
            return []


class ActionRescheduleBooking(Action):
    """
    Reschedules an existing booking to a new date/time.
    
    Required slots:
    - booking_id
    - booking_date (new date)
    - booking_time (new time)
    """
    
    def name(self) -> Text:
        return "action_reschedule_booking"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        booking_id = tracker.get_slot("booking_id")
        new_date = tracker.get_slot("booking_date")
        new_time = tracker.get_slot("booking_time")
        
        if not booking_id:
            dispatcher.utter_message(
                text="I need your booking reference number to reschedule. It looks like BK-XXXX-XXXX."
            )
            return [FollowupAction("booking_lookup_form")]
        
        if not new_date or not new_time:
            dispatcher.utter_message(
                text="I need both a new date and time to reschedule your booking."
            )
            return [FollowupAction("booking_form")]
        
        try:
            api_client = BackendAPIClient()
            
            # Validate new date/time against config
            config_manager = ConfigManager()
            task_config = await config_manager.get_task_config("book_service")
            
            validation_result = ValidationUtils.validate_datetime(
                new_date,
                new_time,
                task_config.get("business_hours", {}),
                task_config.get("blocked_dates", [])
            )
            
            if not validation_result["valid"]:
                dispatcher.utter_message(text=validation_result["message"])
                return []
            
            # Call reschedule endpoint
            response = await api_client.reschedule_booking(
                booking_id=booking_id,
                new_date=new_date,
                new_time=new_time
            )
            
            if response.get("success"):
                await AuditLogger.log_action(
                    action="reschedule_booking",
                    booking_id=booking_id,
                    conversation_id=tracker.sender_id,
                    status="success",
                    metadata={"new_date": new_date, "new_time": new_time}
                )
                
                return [
                    SlotSet("current_booking", response.get("booking")),
                    SlotSet("booking_id", booking_id),
                    SlotSet("booking_date", new_date),
                    SlotSet("booking_time", new_time)
                ]
            else:
                error = response.get("error", "Unable to reschedule")
                dispatcher.utter_message(
                    text=f"I couldn't reschedule that booking: {error}"
                )
                return []
                
        except Exception as e:
            logger.exception(f"Exception during booking reschedule: {str(e)}")
            dispatcher.utter_message(response="utter_booking_error")
            return []


class ActionCheckBookingStatus(Action):
    """
    Retrieves and displays the status of a booking.
    
    Required slots:
    - booking_id
    """
    
    def name(self) -> Text:
        return "action_check_booking_status"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        booking_id = tracker.get_slot("booking_id")
        
        if not booking_id:
            # Check if provided in last message entities
            entities = tracker.latest_message.get("entities", [])
            for entity in entities:
                if entity.get("entity") == "booking_id":
                    booking_id = entity.get("value")
                    break
        
        if not booking_id:
            dispatcher.utter_message(response="utter_ask_booking_id")
            return [FollowupAction("booking_lookup_form")]
        
        try:
            api_client = BackendAPIClient()
            
            response = await api_client.get_booking(booking_id)
            
            if response.get("success"):
                booking = response.get("booking", {})
                
                # Format booking details
                status = booking.get("status", "Unknown")
                service = booking.get("service_type", "Unknown")
                date = booking.get("date", "Unknown")
                time = booking.get("time", "Unknown")
                
                message = (
                    f"📋 **Booking Details**\n\n"
                    f"**Reference:** {booking_id}\n"
                    f"**Status:** {status.capitalize()}\n"
                    f"**Service:** {service.capitalize()}\n"
                    f"**Date:** {date}\n"
                    f"**Time:** {time}\n\n"
                    f"Would you like to reschedule or cancel this booking?"
                )
                
                dispatcher.utter_message(text=message)
                
                return [
                    SlotSet("current_booking", booking),
                    SlotSet("booking_id", booking_id),
                    SlotSet("service_type", service),
                    SlotSet("booking_date", date),
                    SlotSet("booking_time", time)
                ]
            else:
                dispatcher.utter_message(
                    text=f"I couldn't find a booking with reference {booking_id}. Please check the number and try again."
                )
                return [SlotSet("booking_id", None)]
                
        except Exception as e:
            logger.exception(f"Exception during booking status check: {str(e)}")
            dispatcher.utter_message(response="utter_booking_error")
            return []


class ActionGetAvailableSlots(Action):
    """
    Retrieves available booking slots for a given date/service.
    
    Optional slots:
    - service_type
    - booking_date
    """
    
    def name(self) -> Text:
        return "action_get_available_slots"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        service_type = tracker.get_slot("service_type")
        booking_date = tracker.get_slot("booking_date")
        
        try:
            api_client = BackendAPIClient()
            
            # Get available slots from backend
            response = await api_client.get_available_slots(
                service_type=service_type,
                date=booking_date
            )
            
            if response.get("success"):
                slots = response.get("available_slots", [])
                
                if slots:
                    # Format available times
                    date_display = booking_date or "requested date"
                    times_list = ", ".join(slots[:6])  # Show max 6 options
                    
                    if len(slots) > 6:
                        times_list += f" (and {len(slots) - 6} more)"
                    
                    dispatcher.utter_message(
                        text=f"Here are the available times for {date_display}:\n\n{times_list}\n\nWhich time works best for you?"
                    )
                else:
                    dispatcher.utter_message(
                        text=f"I'm sorry, there are no available slots for {booking_date}. Would you like to try a different date?"
                    )
                
                return []
            else:
                dispatcher.utter_message(
                    text="I couldn't retrieve the available times right now. Please try again or contact us directly."
                )
                return []
                
        except Exception as e:
            logger.exception(f"Exception getting available slots: {str(e)}")
            dispatcher.utter_message(
                text="I'm having trouble checking availability. Please try again in a moment."
            )
            return []
