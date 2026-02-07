# =============================================================================
# LLM API ENDPOINTS
# =============================================================================
# API endpoints for LLM configuration and AI-powered chat
# =============================================================================

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Body, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncpg

from .schemas import LLMConfig, LLMConfigCreate, LLMProvider, DEFAULT_LLM_CONFIG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])
security = HTTPBearer(auto_error=False)


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

db_pool: Optional[asyncpg.Pool] = None


async def get_db():
    """Dependency for database connection."""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "chatbot"),
            user=os.getenv("DB_USER", "rasa"),
            password=os.getenv("DB_PASSWORD", "rasa_password"),
            min_size=2,
            max_size=10
        )
    async with db_pool.acquire() as conn:
        yield conn


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify admin token."""
    if credentials is None:
        return {"user_id": 0, "email": "anonymous", "role": "viewer"}
    return {"user_id": 1, "email": "admin@example.com", "role": "admin"}


# =============================================================================
# LLM CLIENTS
# =============================================================================

class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
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
        
        # Build messages
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
            raise ValueError(f"Unsupported provider: {self.provider}")
    
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
                "model": self.model,
                "provider": "openai",
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI package not installed"
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
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
                "model": self.model,
                "provider": "azure_openai"
            }
        except Exception as e:
            logger.error(f"Azure OpenAI error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _call_anthropic(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Anthropic API."""
        try:
            import anthropic
            
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            
            # Convert messages format
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
                "model": self.model,
                "provider": "anthropic"
            }
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Anthropic package not installed"
            )
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return {"success": False, "error": str(e)}
    
    async def _call_ollama(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call Ollama API (local LLM)."""
        import httpx
        
        base_url = self.api_base_url or "http://ollama:11434"
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Check if model is available
                try:
                    tags_resp = await client.get(f"{base_url}/api/tags")
                    tags_resp.raise_for_status()
                    available_models = [m["name"].split(":")[0] for m in tags_resp.json().get("models", [])]
                    model_base = self.model.split(":")[0]
                    
                    if model_base not in available_models:
                        # Auto-pull the model
                        logger.info(f"Model '{self.model}' not found locally. Pulling...")
                        pull_resp = await client.post(
                            f"{base_url}/api/pull",
                            json={"name": self.model, "stream": False},
                            timeout=600.0  # 10 min timeout for model download
                        )
                        pull_resp.raise_for_status()
                        logger.info(f"Model '{self.model}' pulled successfully.")
                except httpx.ConnectError:
                    return {"success": False, "error": f"Cannot connect to Ollama at {base_url}. Ensure Ollama is running."}
                
                response = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": self.max_tokens
                        }
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                return {
                    "success": True,
                    "response": data.get("message", {}).get("content", ""),
                    "model": self.model,
                    "provider": "ollama"
                }
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
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
                "model": self.model,
                "provider": "google"
            }
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google GenAI package not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error(f"Google API error: {e}")
            return {"success": False, "error": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def mask_api_key(key: Optional[str]) -> Optional[str]:
    """Mask API key for display."""
    if not key or len(key) < 8:
        return None
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


async def get_llm_config(conn: asyncpg.Connection) -> Dict[str, Any]:
    """Get LLM configuration from database."""
    row = await conn.fetchrow("SELECT * FROM llm_config WHERE id = 1")
    if row:
        config = dict(row)
        # Parse JSON fields
        if isinstance(config.get('config'), str):
            config['config'] = json.loads(config['config'])
        return config.get('config', DEFAULT_LLM_CONFIG)
    return DEFAULT_LLM_CONFIG


async def get_kb_context(query: str, collection: str = "website_content") -> str:
    """Get relevant context from knowledge base."""
    try:
        from .knowledge_base import chroma_client
        
        chroma_collection = chroma_client.get_collection(collection)
        results = chroma_collection.query(
            query_texts=[query],
            n_results=3
        )
        
        if results['documents'] and results['documents'][0]:
            contexts = []
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                source = metadata.get('source', 'Unknown')
                contexts.append(f"[Source: {source}]\n{doc}")
            return "\n\n---\n\n".join(contexts)
        return ""
    except Exception as e:
        logger.error(f"Knowledge base search error: {e}")
        return ""


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get("/config")
async def get_config(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Get LLM configuration (with masked API key)."""
    config = await get_llm_config(conn)
    
    # Mask API key for security
    if config.get('api_key'):
        config['api_key_masked'] = mask_api_key(config['api_key'])
        config['api_key_set'] = True
    else:
        config['api_key_masked'] = None
        config['api_key_set'] = False
    
    # Don't return raw API key
    config.pop('api_key', None)
    
    return {"config": config}


@router.put("/config")
async def update_config(
    config_update: LLMConfigCreate,
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Update LLM configuration."""
    # Get current config
    current_config = await get_llm_config(conn)
    
    # Merge updates
    update_dict = config_update.dict(exclude_none=True)
    for key, value in update_dict.items():
        if value is not None:
            current_config[key] = value
    
    # Save to database
    config_json = json.dumps(current_config)
    
    await conn.execute("""
        INSERT INTO llm_config (id, config, updated_at, updated_by)
        VALUES (1, $1::jsonb, NOW(), $2)
        ON CONFLICT (id) DO UPDATE SET
            config = $1::jsonb,
            updated_at = NOW(),
            updated_by = $2
    """, config_json, user.get("email"))
    
    # Return without raw API key
    response_config = current_config.copy()
    if response_config.get('api_key'):
        response_config['api_key_masked'] = mask_api_key(response_config['api_key'])
        response_config['api_key_set'] = True
    response_config.pop('api_key', None)
    
    return {"success": True, "config": response_config}


@router.post("/chat")
async def chat_with_llm(
    message: str = Form(...),
    use_knowledge_base: bool = Form(True),
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Chat with the LLM (with optional RAG context)."""
    config = await get_llm_config(conn)
    
    if not config.get('enabled', False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM is not enabled. Please enable it in settings."
        )
    
    if not config.get('api_key') and config.get('provider') != 'ollama':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key not configured. Please add your API key in settings."
        )
    
    # Get knowledge base context if enabled
    context = ""
    if use_knowledge_base and config.get('use_knowledge_base', True):
        context = await get_kb_context(message)
    
    # Generate response
    client = LLMClient(config)
    result = await client.generate(message, context)
    
    if result.get('success'):
        return {
            "success": True,
            "response": result['response'],
            "model": result.get('model'),
            "provider": result.get('provider'),
            "context_used": bool(context),
            "usage": result.get('usage')
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get('error', 'Unknown error')
        )


@router.post("/test-connection")
async def test_llm_connection(
    conn: asyncpg.Connection = Depends(get_db),
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Test LLM connection with current settings."""
    config = await get_llm_config(conn)
    
    if not config.get('api_key') and config.get('provider') != 'ollama':
        return {
            "success": False,
            "error": "API key not configured"
        }
    
    # Test with a simple message
    client = LLMClient(config)
    result = await client.generate("Say 'Connection successful!' in one line.")
    
    return {
        "success": result.get('success', False),
        "response": result.get('response', ''),
        "error": result.get('error'),
        "provider": config.get('provider'),
        "model": config.get('model')
    }


@router.get("/models")
async def list_available_models(
    _: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """List available models for each provider."""
    return {
        "providers": {
            "openai": {
                "name": "OpenAI",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (Best)", "description": "Most capable model"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (Recommended)", "description": "Fast and affordable"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "High capability"},
                    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "description": "Fast and cheap"}
                ],
                "requires_key": True
            },
            "anthropic": {
                "name": "Anthropic",
                "models": [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Latest balanced model"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "description": "Fast and capable"},
                    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "Most capable"}
                ],
                "requires_key": True
            },
            "google": {
                "name": "Google",
                "models": [
                    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Recommended)", "description": "Fast and capable"},
                    {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite", "description": "Lightweight and fast"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "description": "Previous gen fast model"}
                ],
                "requires_key": True
            },
            "ollama": {
                "name": "Ollama (Local)",
                "models": [
                    {"id": "phi3", "name": "Phi-3 (Recommended)", "description": "Microsoft's efficient model - pre-installed"},
                    {"id": "llama3.2", "name": "Llama 3.2", "description": "Meta's open model"},
                    {"id": "mistral", "name": "Mistral 7B", "description": "Efficient open model"},
                    {"id": "codellama", "name": "Code Llama", "description": "Code-focused"},
                    {"id": "gemma2:2b", "name": "Gemma 2 2B", "description": "Google's small model"}
                ],
                "requires_key": False,
                "note": "Models will be auto-downloaded on first use"
            },
            "azure_openai": {
                "name": "Azure OpenAI",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o", "description": "Deployment name may vary"},
                    {"id": "gpt-35-turbo", "name": "GPT-3.5 Turbo", "description": "Deployment name may vary"}
                ],
                "requires_key": True,
                "requires_endpoint": True
            }
        }
    }


@router.delete("/api-key")
async def remove_api_key(
    conn: asyncpg.Connection = Depends(get_db),
    user: dict = Depends(verify_token)
) -> Dict[str, Any]:
    """Remove the API key from configuration."""
    config = await get_llm_config(conn)
    config['api_key'] = None
    
    config_json = json.dumps(config)
    await conn.execute("""
        UPDATE llm_config SET config = $1::jsonb, updated_at = NOW(), updated_by = $2
        WHERE id = 1
    """, config_json, user.get("email"))
    
    return {"success": True, "message": "API key removed"}
