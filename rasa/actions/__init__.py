# =============================================================================
# RASA CUSTOM ACTIONS - Main Entry Point
# =============================================================================
# This module exports all custom actions for the RASA action server.
# Actions are organized into separate modules for maintainability.
# =============================================================================

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, AllSlotsReset, FollowupAction

# Import all action modules
from .booking_actions import (
    ActionCreateBooking,
    ActionCancelBooking,
    ActionRescheduleBooking,
    ActionCheckBookingStatus,
    ActionGetAvailableSlots,
)

from .meeting_actions import (
    ActionScheduleMeeting,
    ActionGetAvailableMeetingTimes,
)

from .qa_actions import (
    ActionAnswerQuestion,
    ActionSearchKnowledgeBase,
)

from .validation_actions import (
    ValidateBookingForm,
    ValidateMeetingForm,
    ValidateBookingLookupForm,
)

from .config_actions import (
    ActionCheckTaskEnabled,
    ActionGetTaskConfig,
)

from .utility_actions import (
    ActionExtractDate,
    ActionExtractTime,
    ActionResetSlots,
    ActionLogInteraction,
    ActionHandoffToHuman,
    ActionCollectCallbackInfo,
)

# Export all actions
__all__ = [
    # Booking Actions
    "ActionCreateBooking",
    "ActionCancelBooking",
    "ActionRescheduleBooking",
    "ActionCheckBookingStatus",
    "ActionGetAvailableSlots",
    
    # Meeting Actions
    "ActionScheduleMeeting",
    "ActionGetAvailableMeetingTimes",
    
    # Q&A Actions
    "ActionAnswerQuestion",
    "ActionSearchKnowledgeBase",
    
    # Validation Actions
    "ValidateBookingForm",
    "ValidateMeetingForm",
    "ValidateBookingLookupForm",
    
    # Config Actions
    "ActionCheckTaskEnabled",
    "ActionGetTaskConfig",
    
    # Utility Actions
    "ActionExtractDate",
    "ActionExtractTime",
    "ActionResetSlots",
    "ActionLogInteraction",
    "ActionHandoffToHuman",
    "ActionCollectCallbackInfo",
]
