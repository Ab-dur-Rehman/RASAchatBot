# =============================================================================
# UTILITY ACTIONS
# =============================================================================
# General utility actions: slot reset, date/time extraction, logging, handoff
# =============================================================================

import logging
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset

from .utils.validators import ValidationUtils
from .utils.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class ActionExtractDate(Action):
    """
    Extracts and normalizes date from user message using Duckling.
    """
    
    def name(self) -> Text:
        return "action_extract_date"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Get entities from the latest message
        entities = tracker.latest_message.get("entities", [])
        
        # Look for time/date entities from Duckling
        for entity in entities:
            if entity.get("entity") == "time":
                # Duckling provides structured time data
                value = entity.get("value")
                additional_info = entity.get("additional_info", {})
                
                # Extract date if available
                if value:
                    date = ValidationUtils.parse_date(value)
                    if date:
                        return [SlotSet("booking_date", date.strftime("%Y-%m-%d"))]
        
        return []


class ActionExtractTime(Action):
    """
    Extracts and normalizes time from user message.
    """
    
    def name(self) -> Text:
        return "action_extract_time"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        entities = tracker.latest_message.get("entities", [])
        
        for entity in entities:
            if entity.get("entity") == "time":
                value = entity.get("value")
                
                if value:
                    time = ValidationUtils.parse_time(value)
                    if time:
                        return [SlotSet("booking_time", time.strftime("%H:%M"))]
        
        return []


class ActionResetSlots(Action):
    """
    Resets booking/meeting slots to start fresh.
    """
    
    def name(self) -> Text:
        return "action_reset_slots"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Slots to reset
        slots_to_reset = [
            "service_type",
            "booking_date",
            "booking_time",
            "customer_name",
            "customer_email",
            "customer_phone",
            "party_size",
            "meeting_type",
            "meeting_date",
            "meeting_time",
            "meeting_duration",
            "attendee_email",
            "meeting_notes",
            "booking_id",
            "current_booking",
            "confirmed",
            "qa_answer",
            "qa_source"
        ]
        
        return [SlotSet(slot, None) for slot in slots_to_reset]


class ActionLogInteraction(Action):
    """
    Logs conversation interactions for analytics.
    """
    
    def name(self) -> Text:
        return "action_log_interaction"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Extract interaction data
        intent = tracker.latest_message.get("intent", {}).get("name", "unknown")
        confidence = tracker.latest_message.get("intent", {}).get("confidence", 0)
        entities = tracker.latest_message.get("entities", [])
        
        # Log interaction (non-PII)
        await AuditLogger.log_interaction(
            conversation_id=tracker.sender_id,
            intent=intent,
            confidence=confidence,
            entity_count=len(entities),
            slot_fill_status=self._get_slot_status(tracker)
        )
        
        return []
    
    def _get_slot_status(self, tracker: Tracker) -> Dict:
        """Get current slot fill status for analytics."""
        important_slots = [
            "service_type", "booking_date", "booking_time",
            "customer_name", "customer_email"
        ]
        
        return {
            slot: tracker.get_slot(slot) is not None 
            for slot in important_slots
        }


class ActionHandoffToHuman(Action):
    """
    Initiates handoff to human agent.
    """
    
    def name(self) -> Text:
        return "action_handoff_to_human"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Get conversation context for the human agent
        active_loop = tracker.active_loop.get("name") if tracker.active_loop else None
        slots = tracker.current_slot_values()
        
        # Log handoff request
        await AuditLogger.log_action(
            action="handoff_to_human",
            conversation_id=tracker.sender_id,
            status="initiated",
            metadata={
                "active_loop": active_loop,
                "reason": tracker.latest_message.get("text", "")[:100]
            }
        )
        
        # In a real implementation, this would:
        # 1. Notify the live chat system
        # 2. Transfer the conversation context
        # 3. Potentially create a support ticket
        
        # For now, provide user with options
        handoff_message = (
            "I understand you'd like to speak with a human agent.\n\n"
            "Here are your options:\n"
            "📞 Call us: (555) 123-4567\n"
            "📧 Email: support@example.com\n"
            "💬 Live chat: Available Mon-Fri 9AM-5PM\n\n"
            "If you'd like, I can collect your contact information and have someone reach out to you."
        )
        
        dispatcher.utter_message(text=handoff_message)
        
        # Check if we're in a live chat environment
        # If so, trigger actual handoff
        channel = tracker.get_latest_input_channel()
        if channel in ["socketio", "websocket"]:
            # Emit handoff event for live chat system
            dispatcher.utter_message(
                json_message={
                    "event": "handoff_request",
                    "conversation_id": tracker.sender_id,
                    "context": {
                        "active_loop": active_loop,
                        "last_intent": tracker.latest_message.get("intent", {}).get("name"),
                        "slots": {k: v for k, v in slots.items() if v is not None}
                    }
                }
            )
        
        return []


class ActionCollectCallbackInfo(Action):
    """
    Collects user contact information for callback.
    """
    
    def name(self) -> Text:
        return "action_collect_callback_info"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Check if we already have contact info
        email = tracker.get_slot("customer_email")
        phone = tracker.get_slot("customer_phone")
        
        if email or phone:
            dispatcher.utter_message(
                text="Thanks! We have your contact information on file. "
                     "Someone from our team will reach out to you within 24 hours."
            )
            
            # Log callback request
            await AuditLogger.log_action(
                action="callback_request",
                conversation_id=tracker.sender_id,
                status="created",
                metadata={
                    "has_email": email is not None,
                    "has_phone": phone is not None
                }
            )
            
            return []
        
        # Ask for contact information
        dispatcher.utter_message(response="utter_collect_contact_for_callback")
        
        return []
