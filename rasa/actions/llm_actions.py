# =============================================================================
# LLM ACTIONS - AI-Powered Response Generation
# =============================================================================
# Custom actions for LLM-based responses with optional RAG context
# =============================================================================

import os
import json
import logging
import asyncio
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
        elif self.provider == "azure_openai":
            return await self._call_azure_openai(messages)
        elif self.provider == "anthropic":
            return await self._call_anthropic(messages)
        elif self.provider == "ollama":
            return await self._call_ollama(messages)
        elif self.provider == "google":
            return await self._call_google(messages)
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
            
            # Concatenate all system messages
            system_parts = [m["content"] for m in messages if m["role"] == "system"]
            system_msg = "\n\n".join(system_parts) if system_parts else ""
            
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
    
    async def _call_azure_openai(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Azure OpenAI API."""
        try:
            import openai
            
            client = openai.AsyncAzureOpenAI(
                api_key=self.api_key,
                api_version="2024-02-15-preview",
                azure_endpoint=self.api_base_url
            )
            
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
            logger.error(f"Azure OpenAI error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _call_ollama(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Ollama API with auto-pull support."""
        import aiohttp
        
        base_url = self.api_base_url or "http://ollama:11434"
        
        try:
            async with aiohttp.ClientSession() as session:
                # Check if model is available and auto-pull if not
                try:
                    async with session.get(
                        f"{base_url}/api/tags",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as tags_resp:
                        tags_data = await tags_resp.json()
                        available = [m["name"].split(":")[0] for m in tags_data.get("models", [])]
                        model_base = self.model.split(":")[0]
                        
                        if model_base not in available:
                            logger.info(f"Pulling Ollama model '{self.model}'...")
                            async with session.post(
                                f"{base_url}/api/pull",
                                json={"name": self.model, "stream": False},
                                timeout=aiohttp.ClientTimeout(total=600)
                            ) as pull_resp:
                                await pull_resp.json()
                            logger.info(f"Model '{self.model}' pulled successfully.")
                except aiohttp.ClientConnectorError:
                    return {"success": False, "error": f"Cannot connect to Ollama at {base_url}"}
                
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
                    timeout=aiohttp.ClientTimeout(total=120)
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
    
    async def _call_google(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Google Gemini API."""
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.api_key)
            
            # Extract system prompt and build contents
            system_prompt = None
            contents = []
            for m in messages:
                if m["role"] == "system":
                    if system_prompt is None:
                        system_prompt = m["content"]
                    else:
                        system_prompt += "\n" + m["content"]
                else:
                    role = "model" if m["role"] == "assistant" else "user"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=m["content"])]
                        )
                    )
            
            config = types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
            if system_prompt:
                config.system_instruction = system_prompt
            
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            
            return {
                "success": True,
                "response": response.text,
                "model": self.model
            }
        except Exception as e:
            logger.error(f"Google Gemini error: {e}")
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
    Smart fallback action for when RASA NLU confidence is low.
    
    Follows this priority chain:
    1. Search Knowledge Base - if good results found, answer directly
    2. Use LLM (with KB context if available) - if LLM is configured
    3. Default response - if neither KB nor LLM can answer
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
        
        logger.info(
            f"Fallback triggered. Intent: {intent.get('name')}, "
            f"Confidence: {confidence:.3f}, Message: '{user_message}'"
        )
        
        # =================================================================
        # STEP 1: Try Knowledge Base first (no LLM config required)
        # =================================================================
        kb_results = []
        try:
            kb_client = KnowledgeBaseClient()
            kb_results = await kb_client.search(
                query=user_message,
                top_k=3,
                min_score=0.65
            )
            logger.info(f"KB search returned {len(kb_results)} results")
        except Exception as e:
            logger.warning(f"KB search in fallback failed: {e}")
        
        if kb_results:
            top_result = kb_results[0]
            logger.info(
                f"KB hit: score={top_result.get('score')}, "
                f"source={top_result.get('source')}"
            )
            
            # Return KB results directly
            content = top_result.get("content", "")[:500]
            source = top_result.get("source", "Knowledge Base")
            dispatcher.utter_message(
                text=f"Here's what I found:\n\n{content}\n\n"
                     f"📖 *Source: {source}*"
            )
            return []
        
        # =================================================================
        # STEP 2: No KB results - Try LLM (if configured)
        # =================================================================
        llm_config = await get_llm_config()
        
        if (llm_config and llm_config.get("enabled") and
                llm_config.get("fallback_to_llm", False) and
                (llm_config.get("api_key") or
                 llm_config.get("provider") == "ollama")):
            try:
                client = LLMClient(llm_config)
                result = await asyncio.wait_for(
                    client.generate(user_message),
                    timeout=15.0
                )
                
                if result.get("success"):
                    response_text = result["response"]
                    response_text += (
                        "\n\n_Note: I'm answering based on "
                        "my general knowledge._"
                    )
                    dispatcher.utter_message(text=response_text)
                    return [SlotSet("llm_response", response_text)]
            except asyncio.TimeoutError:
                logger.warning("LLM direct response timed out")
            except Exception as e:
                logger.error(f"LLM fallback error: {e}")
        else:
            logger.info("LLM not configured or disabled, skipping")

        # =================================================================
        # STEP 3: Neither KB nor LLM answered - use default response
        # =================================================================
        logger.info("No answer from KB or LLM, using default response")
        dispatcher.utter_message(response="utter_default")
        return []
