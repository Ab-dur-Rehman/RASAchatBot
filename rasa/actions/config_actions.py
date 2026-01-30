# =============================================================================
# CONFIGURATION ACTIONS
# =============================================================================
# Actions for reading and applying runtime task configuration
# =============================================================================

import logging
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from .utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class ActionCheckTaskEnabled(Action):
    """
    Checks if a specific task is enabled in the admin configuration.
    
    This action:
    1. Determines which task is being requested
    2. Queries the config API for task status
    3. Sets the task_enabled slot accordingly
    """
    
    def name(self) -> Text:
        return "action_check_task_enabled"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Determine which task is being requested based on intent
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        
        # Map intents to task names
        intent_to_task = {
            "book_service": "book_service",
            "schedule_meeting": "schedule_meeting",
            "cancel_booking": "cancel_booking",
            "reschedule_booking": "reschedule_booking",
            "check_booking": "check_booking"
        }
        
        task_name = intent_to_task.get(intent, intent)
        
        try:
            # Get task configuration
            config_manager = ConfigManager()
            task_config = await config_manager.get_task_config(task_name)
            
            if task_config:
                is_enabled = task_config.get("enabled", True)
                
                if not is_enabled:
                    logger.info(f"Task '{task_name}' is disabled in configuration")
                    return [SlotSet("task_enabled", False)]
                
                # Check additional conditions (business hours, etc.)
                if not self._check_business_hours(task_config):
                    dispatcher.utter_message(
                        text="I'm sorry, this service is not available right now. "
                             "Please try during our business hours or contact us directly."
                    )
                    return [SlotSet("task_enabled", False)]
                
                return [SlotSet("task_enabled", True)]
            else:
                # No config found, default to enabled
                logger.warning(f"No configuration found for task '{task_name}', defaulting to enabled")
                return [SlotSet("task_enabled", True)]
                
        except Exception as e:
            logger.exception(f"Error checking task config: {str(e)}")
            # On error, default to enabled but log the issue
            return [SlotSet("task_enabled", True)]
    
    def _check_business_hours(self, task_config: Dict) -> bool:
        """
        Check if current time is within business hours.
        """
        from datetime import datetime
        
        business_hours = task_config.get("business_hours")
        if not business_hours:
            return True
        
        # Get current hour
        current_hour = datetime.now().hour
        
        try:
            start_hour = int(business_hours.get("start", "00:00").split(":")[0])
            end_hour = int(business_hours.get("end", "23:59").split(":")[0])
            
            return start_hour <= current_hour < end_hour
        except (ValueError, AttributeError):
            return True


class ActionGetTaskConfig(Action):
    """
    Retrieves full task configuration for use in forms/actions.
    Stores config in a slot for other actions to use.
    """
    
    def name(self) -> Text:
        return "action_get_task_config"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        
        # Determine task name
        task_name = None
        if "book" in intent:
            task_name = "book_service"
        elif "meeting" in intent:
            task_name = "schedule_meeting"
        
        if not task_name:
            return []
        
        try:
            config_manager = ConfigManager()
            task_config = await config_manager.get_task_config(task_name)
            
            if task_config:
                # Extract key configuration for the conversation
                services = task_config.get("services", [])
                enabled_services = [
                    s.get("name", s) if isinstance(s, dict) else s 
                    for s in services 
                    if not isinstance(s, dict) or s.get("enabled", True)
                ]
                
                # Send available options to user if relevant
                if task_name == "book_service" and enabled_services:
                    services_text = ", ".join(enabled_services)
                    dispatcher.utter_message(
                        text=f"We offer the following services: {services_text}"
                    )
            
            return []
            
        except Exception as e:
            logger.exception(f"Error getting task config: {str(e)}")
            return []
