# =============================================================================
# LLM ACTIONS - AI-Powered Response Generation
# =============================================================================
# Custom actions for LLM-based responses with optional RAG context
# =============================================================================

import os
import json
import logging
from typing import Any, Dict, List, Text, Optional

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from .utils.knowledge_base import KnowledgeBaseClient

logger = logging.getLogger(__name__)

# Configuration
ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin-api:8080")


class LLMClient:
    """Client for LLM API calls."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("provider", "openai")
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key = config.get("api_key")
        self.api_base_url = config.get("api_base_url")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 500)
        self.system_prompt = config.get("system_prompt", "You are a helpful assistant.")
    
    async def generate(self, user_message: str, context: str = "") -> Dict[str, Any]:
        """Generate a response using the configured LLM."""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        if context:
            messages.append({
                "role": "system",
                "content": f"Use this context to answer the user's question:\n\n{context}"
            })
        
        messages.append({"role": "user", "content": user_message})
        
        if self.provider == "openai":
            return await self._call_openai(messages)
        elif self.provider == "anthropic":
            return await self._call_anthropic(messages)
        elif self.provider == "ollama":
            return await self._call_ollama(messages)
        else:
            return await self._call_openai(messages)  # Default to OpenAI
    
    async def _call_openai(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call OpenAI API."""
        try:
            import openai
            
            client = openai.AsyncOpenAI(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return {
                "success": True,
                "response": response.choices[0].message.content,
                "model": self.model
            }
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _call_anthropic(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Anthropic API."""
        try:
            import anthropic
            
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            
            system_msg = messages[0]["content"] if messages[0]["role"] == "system" else ""
            anthropic_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in messages if m["role"] != "system"
            ]
            
            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_msg,
                messages=anthropic_messages
            )
            
            return {
                "success": True,
                "response": response.content[0].text,
                "model": self.model
            }
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _call_ollama(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Ollama API."""
        import aiohttp
        
        base_url = self.api_base_url or "http://ollama:11434"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": self.max_tokens
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    data = await response.json()
                    return {
                        "success": True,
                        "response": data.get("message", {}).get("content", ""),
                        "model": self.model
                    }
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return {"success": False, "error": str(e)}


async def get_llm_config() -> Optional[Dict[str, Any]]:
    """Get LLM configuration from admin API."""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ADMIN_API_URL}/api/llm/config",
                headers={"Authorization": "Bearer internal"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("config")
    except Exception as e:
        logger.error(f"Failed to get LLM config: {e}")
    
    return None


class ActionAnswerFromKnowledgeBase(Action):
    """
    Answers questions using RAG (Retrieval-Augmented Generation).
    
    This action:
    1. Searches the knowledge base for relevant content
    2. Optionally uses LLM to generate a response
    3. Falls back to direct retrieval if LLM is disabled
    """
    
    def name(self) -> Text:
        return "action_answer_from_knowledge_base"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get("text", "")
        
        try:
            # Search knowledge base
            kb_client = KnowledgeBaseClient()
            results = await kb_client.search(
                query=user_message,
                top_k=3,
                min_score=0.5
            )
            
            if not results:
                dispatcher.utter_message(
                    text="I couldn't find relevant information in my knowledge base. "
                         "Could you rephrase your question or ask something else?"
                )
                return []
            
            # Get LLM config
            llm_config = await get_llm_config()
            
            if llm_config and llm_config.get("enabled") and llm_config.get("api_key"):
                # Use LLM with RAG context
                context = "\n\n---\n\n".join([
                    f"[Source: {r.get('source', 'Unknown')}]\n{r.get('content', '')}"
                    for r in results
                ])
                
                client = LLMClient(llm_config)
                llm_result = await client.generate(user_message, context)
                
                if llm_result.get("success"):
                    response_text = llm_result["response"]
                    source = results[0].get("source", "Knowledge Base")
                    
                    dispatcher.utter_message(
                        text=f"{response_text}\n\n📖 *Source: {source}*"
                    )
                    return [SlotSet("llm_response", response_text)]
            
            # Fallback: Return top result directly
            top_result = results[0]
            content = top_result.get("content", "")[:500]
            source = top_result.get("source", "Knowledge Base")
            
            dispatcher.utter_message(
                text=f"Here's what I found:\n\n{content}\n\n📖 *Source: {source}*"
            )
            
            return []
            
        except Exception as e:
            logger.error(f"Knowledge base search error: {e}")
            dispatcher.utter_message(
                text="I'm sorry, I couldn't search my knowledge base right now. "
                     "Please try again later."
            )
            return []


class ActionLLMResponse(Action):
    """
    Generates a response using LLM directly (without RAG).
    
    Use this for general conversation or when knowledge base is not relevant.
    """
    
    def name(self) -> Text:
        return "action_llm_response"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get("text", "")
        
        # Get LLM config
        llm_config = await get_llm_config()
        
        if not llm_config or not llm_config.get("enabled"):
            dispatcher.utter_message(response="utter_llm_unavailable")
            return []
        
        if not llm_config.get("api_key") and llm_config.get("provider") != "ollama":
            dispatcher.utter_message(response="utter_llm_unavailable")
            return []
        
        try:
            # Check if we should use knowledge base
            context = ""
            if llm_config.get("use_knowledge_base", True):
                try:
                    kb_client = KnowledgeBaseClient()
                    results = await kb_client.search(query=user_message, top_k=2)
                    if results:
                        context = "\n\n".join([
                            f"[{r.get('source', 'Unknown')}]: {r.get('content', '')}"
                            for r in results
                        ])
                except Exception as e:
                    logger.warning(f"KB search failed, continuing without context: {e}")
            
            # Generate response
            client = LLMClient(llm_config)
            result = await client.generate(user_message, context)
            
            if result.get("success"):
                dispatcher.utter_message(text=result["response"])
                return [SlotSet("llm_response", result["response"])]
            else:
                logger.error(f"LLM generation failed: {result.get('error')}")
                dispatcher.utter_message(response="utter_llm_unavailable")
                return []
                
        except Exception as e:
            logger.error(f"LLM response error: {e}")
            dispatcher.utter_message(response="utter_llm_unavailable")
            return []


class ActionLLMFallback(Action):
    """
    LLM fallback action for when RASA confidence is low.
    
    This action is triggered by the FallbackClassifier when confidence
    is below the threshold. It uses the LLM to generate a response.
    """
    
    def name(self) -> Text:
        return "action_llm_fallback"
    
    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get("text", "")
        intent = tracker.latest_message.get("intent", {})
        confidence = intent.get("confidence", 0)
        
        logger.info(f"LLM fallback triggered. Intent: {intent.get('name')}, Confidence: {confidence}")
        
        # Get LLM config
        llm_config = await get_llm_config()
        
        if not llm_config or not llm_config.get("fallback_to_llm", False):
            # LLM fallback not enabled, use default response
            dispatcher.utter_message(response="utter_default")
            return []
        
        if not llm_config.get("enabled"):
            dispatcher.utter_message(response="utter_default")
            return []
        
        threshold = llm_config.get("confidence_threshold", 0.6)
        
        # Only use LLM if confidence is below threshold
        if confidence >= threshold:
            dispatcher.utter_message(response="utter_default")
            return []
        
        if not llm_config.get("api_key") and llm_config.get("provider") != "ollama":
            dispatcher.utter_message(response="utter_default")
            return []
        
        try:
            # Try knowledge base first
            context = ""
            if llm_config.get("use_knowledge_base", True):
                try:
                    kb_client = KnowledgeBaseClient()
                    results = await kb_client.search(query=user_message, top_k=3)
                    if results:
                        context = "\n\n".join([
                            f"[{r.get('source', 'Unknown')}]: {r.get('content', '')}"
                            for r in results
                        ])
                except Exception as e:
                    logger.warning(f"KB search in fallback failed: {e}")
            
            # Generate LLM response
            client = LLMClient(llm_config)
            result = await client.generate(user_message, context)
            
            if result.get("success"):
                response_text = result["response"]
                
                # Add helpful note if no context was used
                if not context:
                    response_text += "\n\n_Note: I'm answering based on my general knowledge._"
                
                dispatcher.utter_message(text=response_text)
                return [SlotSet("llm_response", response_text)]
            else:
                dispatcher.utter_message(response="utter_default")
                return []
                
        except Exception as e:
            logger.error(f"LLM fallback error: {e}")
            dispatcher.utter_message(response="utter_default")
            return []
