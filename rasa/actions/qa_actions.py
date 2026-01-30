# =============================================================================
# Q&A ACTIONS - Knowledge Base Retrieval
# =============================================================================
# Custom actions for knowledge-grounded Q&A using vector store retrieval
# =============================================================================

import logging
from typing import Any, Dict, List, Text, Optional

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from .utils.knowledge_base import KnowledgeBaseClient
from .utils.guardrails import GuardrailChecker

logger = logging.getLogger(__name__)


class ActionAnswerQuestion(Action):
    """
    Answers user questions using knowledge base retrieval (RAG).
    
    This action:
    1. Extracts the user's question
    2. Queries the vector store for relevant content
    3. Applies guardrails to ensure answer quality
    4. Responds with answer + source citation
    """
    
    def name(self) -> Text:
        return "action_answer_question"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        # Get the user's question
        user_message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {}).get("name", "")
        entities = tracker.latest_message.get("entities", [])
        
        # Extract specific query context from entities
        info_type = None
        policy_type = None
        for entity in entities:
            if entity.get("entity") == "info_type":
                info_type = entity.get("value")
            elif entity.get("entity") == "policy_type":
                policy_type = entity.get("value")
        
        # Construct search query
        search_query = self._construct_query(user_message, intent, info_type, policy_type)
        
        try:
            # Initialize knowledge base client
            kb_client = KnowledgeBaseClient()
            
            # Perform similarity search
            results = await kb_client.search(
                query=search_query,
                top_k=3,
                min_score=0.65  # Confidence threshold
            )
            
            if results and len(results) > 0:
                # Check if we have a confident answer
                top_result = results[0]
                confidence = top_result.get("score", 0)
                
                # Apply guardrails
                guardrail = GuardrailChecker()
                guardrail_result = await guardrail.check(
                    question=user_message,
                    retrieved_content=results,
                    confidence=confidence
                )
                
                if guardrail_result["should_answer"]:
                    # Construct answer from retrieved content
                    answer = self._construct_answer(results, intent)
                    source = top_result.get("source", "Business Information")
                    
                    # Send response with citation
                    dispatcher.utter_message(
                        text=f"{answer}\n\n📖 *Source: {source}*"
                    )
                    
                    return [
                        SlotSet("qa_answer", answer),
                        SlotSet("qa_source", source)
                    ]
                    
                elif guardrail_result["needs_clarification"]:
                    # Ask for clarification if ambiguous
                    dispatcher.utter_message(response="utter_ask_clarification")
                    return []
                    
                else:
                    # Low confidence - offer alternatives
                    dispatcher.utter_message(response="utter_no_answer_found")
                    return [
                        SlotSet("qa_answer", None),
                        SlotSet("qa_source", None)
                    ]
            else:
                # No relevant results found
                dispatcher.utter_message(response="utter_no_answer_found")
                return [
                    SlotSet("qa_answer", None),
                    SlotSet("qa_source", None)
                ]
                
        except Exception as e:
            logger.exception(f"Exception during Q&A retrieval: {str(e)}")
            dispatcher.utter_message(
                text="I'm having trouble finding that information right now. "
                     "Please try again or contact us directly for assistance."
            )
            return []
    
    def _construct_query(
        self,
        user_message: str,
        intent: str,
        info_type: Optional[str] = None,
        policy_type: Optional[str] = None
    ) -> str:
        """
        Constructs an optimized search query from user input.
        """
        # Map intents to query prefixes for better retrieval
        intent_query_map = {
            "ask_hours": "business hours operating hours open close",
            "ask_pricing": "pricing cost price fees charges",
            "ask_location": "location address directions office",
            "ask_policy": f"{policy_type or ''} policy terms conditions",
            "ask_services": "services offerings products",
            "ask_business_info": "about company business",
            "ask_faq": ""
        }
        
        # Get intent-based prefix
        prefix = intent_query_map.get(intent, "")
        
        # Combine with user message
        query = f"{prefix} {user_message}".strip()
        
        return query
    
    def _construct_answer(
        self,
        results: List[Dict],
        intent: str
    ) -> str:
        """
        Constructs a natural language answer from retrieved results.
        """
        if not results:
            return "I couldn't find specific information about that."
        
        # Get the most relevant content
        top_content = results[0].get("content", "")
        
        # For single clear answer, return directly
        if len(results) == 1 or results[0].get("score", 0) > 0.85:
            return top_content
        
        # For multiple relevant results, combine them
        combined = top_content
        
        # Add secondary info if relevant
        if len(results) > 1 and results[1].get("score", 0) > 0.70:
            secondary = results[1].get("content", "")
            if secondary and secondary not in combined:
                combined = f"{combined}\n\n{secondary}"
        
        return combined


class ActionSearchKnowledgeBase(Action):
    """
    Performs a direct search of the knowledge base.
    Can be used for explicit "search for X" type requests.
    """
    
    def name(self) -> Text:
        return "action_search_knowledge_base"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get("text", "")
        
        # Remove common search prefixes
        search_terms = user_message.lower()
        for prefix in ["search for", "find", "look up", "search"]:
            if search_terms.startswith(prefix):
                search_terms = search_terms[len(prefix):].strip()
        
        try:
            kb_client = KnowledgeBaseClient()
            
            results = await kb_client.search(
                query=search_terms,
                top_k=5,
                min_score=0.5
            )
            
            if results:
                # Format search results
                message = f"Here's what I found for \"{search_terms}\":\n\n"
                
                for i, result in enumerate(results[:3], 1):
                    content = result.get("content", "")[:200]  # Truncate
                    source = result.get("source", "")
                    
                    if len(result.get("content", "")) > 200:
                        content += "..."
                    
                    message += f"**{i}.** {content}\n"
                    if source:
                        message += f"   _Source: {source}_\n"
                    message += "\n"
                
                dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(
                    text=f"I couldn't find any results for \"{search_terms}\". "
                         f"Try rephrasing your search or ask me a specific question."
                )
            
            return []
            
        except Exception as e:
            logger.exception(f"Exception during knowledge base search: {str(e)}")
            dispatcher.utter_message(
                text="I'm having trouble searching right now. Please try again."
            )
            return []
