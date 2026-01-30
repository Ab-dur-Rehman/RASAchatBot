# =============================================================================
# MEETING ACTIONS
# =============================================================================
# Custom actions for meeting scheduling
# =============================================================================

import logging
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction

from .utils.api_client import BackendAPIClient
from .utils.config_manager import ConfigManager
from .utils.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class ActionScheduleMeeting(Action):
    """
    Schedules a meeting via the backend calendar API.
    
    Required slots:
    - meeting_type
    - meeting_date
    - meeting_time
    - meeting_duration
    - attendee_email
    """
    
    def name(self) -> Text:
        return "action_schedule_meeting"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Extract meeting details from slots
        meeting_type = tracker.get_slot("meeting_type")
        meeting_date = tracker.get_slot("meeting_date")
        meeting_time = tracker.get_slot("meeting_time")
        meeting_duration = tracker.get_slot("meeting_duration")
        attendee_email = tracker.get_slot("attendee_email")
        meeting_notes = tracker.get_slot("meeting_notes")
        
        # Validate required fields
        if not all([meeting_type, meeting_date, meeting_time, attendee_email]):
            dispatcher.utter_message(
                text="I need a few more details to schedule your meeting. Let me help you fill in the missing information."
            )
            return [FollowupAction("meeting_form")]
        
        # Default duration if not provided
        if not meeting_duration:
            meeting_duration = "30 minutes"
        
        try:
            api_client = BackendAPIClient()
            
            # Prepare meeting payload
            meeting_payload = {
                "meeting_type": meeting_type,
                "date": meeting_date,
                "time": meeting_time,
                "duration": meeting_duration,
                "attendee_email": attendee_email,
                "notes": meeting_notes or "",
                "source": "chatbot",
                "conversation_id": tracker.sender_id
            }
            
            # Call meeting scheduling API
            response = await api_client.schedule_meeting(meeting_payload)
            
            if response.get("success"):
                meeting_id = response.get("meeting_id")
                calendar_link = response.get("calendar_link", "")
                
                # Log successful scheduling
                await AuditLogger.log_action(
                    action="schedule_meeting",
                    meeting_id=meeting_id,
                    conversation_id=tracker.sender_id,
                    status="success"
                )
                
                # Compose success message
                success_message = (
                    f"✅ Your meeting has been scheduled!\n\n"
                    f"**Meeting Details:**\n"
                    f"• Type: {meeting_type}\n"
                    f"• Date: {meeting_date}\n"
                    f"• Time: {meeting_time}\n"
                    f"• Duration: {meeting_duration}\n\n"
                    f"A calendar invite has been sent to {attendee_email}."
                )
                
                if calendar_link:
                    success_message += f"\n\n[Add to Calendar]({calendar_link})"
                
                dispatcher.utter_message(text=success_message)
                
                return [
                    SlotSet("meeting_id", meeting_id),
                ]
            else:
                error = response.get("error", "Unknown error")
                logger.error(f"Meeting scheduling failed: {error}")
                
                await AuditLogger.log_action(
                    action="schedule_meeting",
                    conversation_id=tracker.sender_id,
                    status="failed",
                    error=error
                )
                
                # Provide helpful error message
                if "conflict" in error.lower() or "unavailable" in error.lower():
                    dispatcher.utter_message(
                        text="That time slot isn't available. Would you like me to show you the available times?"
                    )
                    return [FollowupAction("action_get_available_meeting_times")]
                else:
                    dispatcher.utter_message(
                        text=f"I couldn't schedule the meeting: {error}. Please try again or contact us directly."
                    )
                
                return []
                
        except Exception as e:
            logger.exception(f"Exception during meeting scheduling: {str(e)}")
            dispatcher.utter_message(
                text="I'm having trouble scheduling the meeting right now. Please try again or contact us directly."
            )
            return []


class ActionGetAvailableMeetingTimes(Action):
    """
    Retrieves available meeting times from the calendar system.
    
    Optional slots:
    - meeting_type
    - meeting_date
    - meeting_duration
    """
    
    def name(self) -> Text:
        return "action_get_available_meeting_times"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        meeting_type = tracker.get_slot("meeting_type")
        meeting_date = tracker.get_slot("meeting_date")
        meeting_duration = tracker.get_slot("meeting_duration") or "30 minutes"
        
        try:
            api_client = BackendAPIClient()
            config_manager = ConfigManager()
            
            # Get meeting task configuration
            task_config = await config_manager.get_task_config("schedule_meeting")
            
            # Request available times from backend
            response = await api_client.get_available_meeting_times(
                meeting_type=meeting_type,
                date=meeting_date,
                duration=meeting_duration
            )
            
            if response.get("success"):
                available_times = response.get("available_times", [])
                
                if available_times:
                    # Group times by date if multiple dates returned
                    times_by_date = {}
                    for slot in available_times[:12]:  # Limit to 12 options
                        date = slot.get("date", meeting_date)
                        time = slot.get("time")
                        if date not in times_by_date:
                            times_by_date[date] = []
                        times_by_date[date].append(time)
                    
                    # Format response
                    message = "Here are the available meeting times:\n\n"
                    for date, times in times_by_date.items():
                        message += f"**{date}:**\n"
                        message += "• " + "\n• ".join(times) + "\n\n"
                    
                    message += "Which time works best for you?"
                    
                    dispatcher.utter_message(text=message)
                else:
                    # No availability
                    date_str = meeting_date or "the requested period"
                    dispatcher.utter_message(
                        text=f"Unfortunately, there are no available times for {date_str}. "
                             f"Would you like to try a different date?"
                    )
                
                return []
            else:
                dispatcher.utter_message(
                    text="I couldn't retrieve the available times. Please try again."
                )
                return []
                
        except Exception as e:
            logger.exception(f"Exception getting available meeting times: {str(e)}")
            dispatcher.utter_message(
                text="I'm having trouble checking the calendar. Please try again in a moment."
            )
            return []
