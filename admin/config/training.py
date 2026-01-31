# =============================================================================
# TRAINING API ROUTES
# =============================================================================
# FastAPI routes for managing RASA training data
# =============================================================================

import os
import yaml
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel


router = APIRouter(prefix="/api/training", tags=["training"])

# =============================================================================
# CONFIGURATION
# =============================================================================

RASA_DIR = Path(os.getenv("RASA_DIR", "/app/rasa"))
NLU_FILE = RASA_DIR / "data" / "nlu.yml"
DOMAIN_FILE = RASA_DIR / "domain.yml"
STORIES_FILE = RASA_DIR / "data" / "stories.yml"
RULES_FILE = RASA_DIR / "data" / "rules.yml"
MODELS_DIR = RASA_DIR / "models"


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TrainingExample(BaseModel):
    intent: str
    example: str


class TrainingExamplesRequest(BaseModel):
    examples: List[TrainingExample]


class IntentCreate(BaseModel):
    name: str
    examples: List[str]


class ResponseCreate(BaseModel):
    name: str
    texts: List[str]


class RuleCreate(BaseModel):
    name: str
    intent: str
    action: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def load_yaml_file(file_path: Path) -> Dict:
    """Load a YAML file safely."""
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading {file_path}: {str(e)}")


def save_yaml_file(file_path: Path, data: Dict):
    """Save data to a YAML file."""
    try:
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving {file_path}: {str(e)}")


def parse_nlu_examples(nlu_data: Dict) -> Dict[str, List[str]]:
    """Parse NLU data into intent -> examples mapping."""
    result = {}
    nlu_items = nlu_data.get('nlu', [])
    
    for item in nlu_items:
        if 'intent' in item and 'examples' in item:
            intent_name = item['intent']
            # Parse examples from multiline string
            examples_str = item['examples']
            examples = [
                line.strip().lstrip('- ').strip()
                for line in examples_str.strip().split('\n')
                if line.strip() and line.strip() != '-'
            ]
            result[intent_name] = examples
    
    return result


def format_nlu_examples(intent_examples: Dict[str, List[str]]) -> List[Dict]:
    """Format intent examples back to NLU YAML format."""
    nlu_items = []
    
    for intent_name, examples in intent_examples.items():
        examples_str = '\n'.join([f'    - {ex}' for ex in examples])
        nlu_items.append({
            'intent': intent_name,
            'examples': f"|\n{examples_str}\n"
        })
    
    return nlu_items


# =============================================================================
# ENDPOINTS - INTENTS
# =============================================================================

@router.get("/intents")
async def get_all_intents():
    """Get all intents with their training examples."""
    nlu_data = load_yaml_file(NLU_FILE)
    intent_examples = parse_nlu_examples(nlu_data)
    
    intents = [
        {"name": name, "examples": examples, "count": len(examples)}
        for name, examples in intent_examples.items()
    ]
    
    return {"intents": intents, "total": len(intents)}


@router.get("/intents/{intent_name}")
async def get_intent(intent_name: str):
    """Get a specific intent with its examples."""
    nlu_data = load_yaml_file(NLU_FILE)
    intent_examples = parse_nlu_examples(nlu_data)
    
    if intent_name not in intent_examples:
        raise HTTPException(status_code=404, detail=f"Intent '{intent_name}' not found")
    
    return {
        "name": intent_name,
        "examples": intent_examples[intent_name],
        "count": len(intent_examples[intent_name])
    }


@router.post("/intents")
async def create_intent(intent_data: IntentCreate):
    """Create a new intent with examples."""
    nlu_data = load_yaml_file(NLU_FILE)
    
    if 'nlu' not in nlu_data:
        nlu_data = {'version': '3.1', 'nlu': []}
    
    # Check if intent already exists
    for item in nlu_data['nlu']:
        if item.get('intent') == intent_data.name:
            raise HTTPException(status_code=400, detail=f"Intent '{intent_data.name}' already exists")
    
    # Add new intent
    examples_str = '|\n' + '\n'.join([f'    - {ex}' for ex in intent_data.examples]) + '\n'
    nlu_data['nlu'].append({
        'intent': intent_data.name,
        'examples': examples_str
    })
    
    save_yaml_file(NLU_FILE, nlu_data)
    
    # Also add to domain.yml intents list
    domain_data = load_yaml_file(DOMAIN_FILE)
    if 'intents' not in domain_data:
        domain_data['intents'] = []
    if intent_data.name not in domain_data['intents']:
        domain_data['intents'].append(intent_data.name)
        save_yaml_file(DOMAIN_FILE, domain_data)
    
    return {"message": f"Intent '{intent_data.name}' created", "examples_count": len(intent_data.examples)}


@router.put("/intents/{intent_name}")
async def update_intent(intent_name: str, intent_data: IntentCreate):
    """Update an existing intent's examples."""
    nlu_data = load_yaml_file(NLU_FILE)
    
    found = False
    for item in nlu_data.get('nlu', []):
        if item.get('intent') == intent_name:
            examples_str = '|\n' + '\n'.join([f'    - {ex}' for ex in intent_data.examples]) + '\n'
            item['examples'] = examples_str
            found = True
            break
    
    if not found:
        raise HTTPException(status_code=404, detail=f"Intent '{intent_name}' not found")
    
    save_yaml_file(NLU_FILE, nlu_data)
    
    return {"message": f"Intent '{intent_name}' updated", "examples_count": len(intent_data.examples)}


@router.delete("/intents/{intent_name}")
async def delete_intent(intent_name: str):
    """Delete an intent."""
    nlu_data = load_yaml_file(NLU_FILE)
    
    original_count = len(nlu_data.get('nlu', []))
    nlu_data['nlu'] = [item for item in nlu_data.get('nlu', []) if item.get('intent') != intent_name]
    
    if len(nlu_data['nlu']) == original_count:
        raise HTTPException(status_code=404, detail=f"Intent '{intent_name}' not found")
    
    save_yaml_file(NLU_FILE, nlu_data)
    
    # Also remove from domain.yml
    domain_data = load_yaml_file(DOMAIN_FILE)
    if intent_name in domain_data.get('intents', []):
        domain_data['intents'].remove(intent_name)
        save_yaml_file(DOMAIN_FILE, domain_data)
    
    return {"message": f"Intent '{intent_name}' deleted"}


# =============================================================================
# ENDPOINTS - EXAMPLES
# =============================================================================

@router.post("/examples")
async def add_training_examples(request: TrainingExamplesRequest):
    """Add multiple training examples to existing or new intents."""
    nlu_data = load_yaml_file(NLU_FILE)
    
    if 'nlu' not in nlu_data:
        nlu_data = {'version': '3.1', 'nlu': []}
    
    # Group examples by intent
    examples_by_intent: Dict[str, List[str]] = {}
    for ex in request.examples:
        if ex.intent not in examples_by_intent:
            examples_by_intent[ex.intent] = []
        examples_by_intent[ex.intent].append(ex.example)
    
    # Update existing intents or create new ones
    existing_intents = {item['intent']: item for item in nlu_data['nlu'] if 'intent' in item}
    
    for intent_name, new_examples in examples_by_intent.items():
        if intent_name in existing_intents:
            # Add to existing intent
            item = existing_intents[intent_name]
            current_examples = [
                line.strip().lstrip('- ').strip()
                for line in item['examples'].strip().split('\n')
                if line.strip() and line.strip() != '-' and line.strip() != '|'
            ]
            all_examples = list(set(current_examples + new_examples))  # Dedupe
            item['examples'] = '|\n' + '\n'.join([f'    - {ex}' for ex in all_examples]) + '\n'
        else:
            # Create new intent
            examples_str = '|\n' + '\n'.join([f'    - {ex}' for ex in new_examples]) + '\n'
            nlu_data['nlu'].append({
                'intent': intent_name,
                'examples': examples_str
            })
    
    save_yaml_file(NLU_FILE, nlu_data)
    
    # Update domain.yml intents
    domain_data = load_yaml_file(DOMAIN_FILE)
    if 'intents' not in domain_data:
        domain_data['intents'] = []
    
    for intent_name in examples_by_intent.keys():
        if intent_name not in domain_data['intents']:
            domain_data['intents'].append(intent_name)
    
    save_yaml_file(DOMAIN_FILE, domain_data)
    
    return {
        "message": "Examples added successfully",
        "intents_updated": list(examples_by_intent.keys()),
        "total_examples_added": len(request.examples)
    }


# =============================================================================
# ENDPOINTS - RESPONSES
# =============================================================================

@router.get("/responses")
async def get_all_responses():
    """Get all bot responses."""
    domain_data = load_yaml_file(DOMAIN_FILE)
    responses = domain_data.get('responses', {})
    
    return {"responses": responses, "total": len(responses)}


@router.get("/responses/{response_name}")
async def get_response(response_name: str):
    """Get a specific response."""
    domain_data = load_yaml_file(DOMAIN_FILE)
    responses = domain_data.get('responses', {})
    
    if response_name not in responses:
        raise HTTPException(status_code=404, detail=f"Response '{response_name}' not found")
    
    return {"name": response_name, "texts": responses[response_name]}


@router.post("/responses")
async def create_or_update_response(response_data: ResponseCreate):
    """Create or update a bot response."""
    domain_data = load_yaml_file(DOMAIN_FILE)
    
    if 'responses' not in domain_data:
        domain_data['responses'] = {}
    
    # Format response texts
    response_items = [{"text": text} for text in response_data.texts]
    domain_data['responses'][response_data.name] = response_items
    
    # Add to actions if not present
    if 'actions' not in domain_data:
        domain_data['actions'] = []
    if response_data.name not in domain_data['actions']:
        domain_data['actions'].append(response_data.name)
    
    save_yaml_file(DOMAIN_FILE, domain_data)
    
    return {"message": f"Response '{response_data.name}' saved", "texts_count": len(response_data.texts)}


@router.delete("/responses/{response_name}")
async def delete_response(response_name: str):
    """Delete a response."""
    domain_data = load_yaml_file(DOMAIN_FILE)
    
    if response_name not in domain_data.get('responses', {}):
        raise HTTPException(status_code=404, detail=f"Response '{response_name}' not found")
    
    del domain_data['responses'][response_name]
    
    # Remove from actions
    if response_name in domain_data.get('actions', []):
        domain_data['actions'].remove(response_name)
    
    save_yaml_file(DOMAIN_FILE, domain_data)
    
    return {"message": f"Response '{response_name}' deleted"}


# =============================================================================
# ENDPOINTS - RULES
# =============================================================================

@router.get("/rules")
async def get_all_rules():
    """Get all conversation rules."""
    rules_data = load_yaml_file(RULES_FILE)
    rules = rules_data.get('rules', [])
    
    return {"rules": rules, "total": len(rules)}


@router.post("/rules")
async def create_rule(rule_data: RuleCreate):
    """Create a new conversation rule."""
    rules_data = load_yaml_file(RULES_FILE)
    
    if 'rules' not in rules_data:
        rules_data = {'version': '3.1', 'rules': []}
    
    # Check if rule with same name exists
    for rule in rules_data['rules']:
        if rule.get('rule') == rule_data.name:
            raise HTTPException(status_code=400, detail=f"Rule '{rule_data.name}' already exists")
    
    # Add new rule
    new_rule = {
        'rule': rule_data.name,
        'steps': [
            {'intent': rule_data.intent},
            {'action': rule_data.action}
        ]
    }
    rules_data['rules'].append(new_rule)
    
    save_yaml_file(RULES_FILE, rules_data)
    
    return {"message": f"Rule '{rule_data.name}' created"}


# =============================================================================
# ENDPOINTS - TRAINING
# =============================================================================

training_status = {"is_training": False, "last_trained": None, "last_error": None}


def run_training():
    """Background task to run RASA training."""
    global training_status
    training_status["is_training"] = True
    training_status["last_error"] = None
    
    try:
        # Run RASA train command
        result = subprocess.run(
            ["rasa", "train", "--force"],
            cwd=str(RASA_DIR),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode == 0:
            training_status["last_trained"] = datetime.utcnow().isoformat()
        else:
            training_status["last_error"] = result.stderr
            
    except subprocess.TimeoutExpired:
        training_status["last_error"] = "Training timed out after 10 minutes"
    except Exception as e:
        training_status["last_error"] = str(e)
    finally:
        training_status["is_training"] = False


@router.post("/train")
async def train_model(background_tasks: BackgroundTasks):
    """Start model training in the background."""
    if training_status["is_training"]:
        raise HTTPException(status_code=409, detail="Training already in progress")
    
    background_tasks.add_task(run_training)
    
    return {"message": "Training started", "status": "in_progress"}


@router.get("/train/status")
async def get_training_status():
    """Get current training status."""
    return training_status


@router.get("/models")
async def list_models():
    """List all trained models."""
    models = []
    
    if MODELS_DIR.exists():
        for model_file in MODELS_DIR.glob("*.tar.gz"):
            stat = model_file.stat()
            models.append({
                "name": model_file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    
    # Sort by creation date, newest first
    models.sort(key=lambda x: x["created"], reverse=True)
    
    return {"models": models, "total": len(models)}


# =============================================================================
# ENDPOINTS - DOMAIN OVERVIEW
# =============================================================================

@router.get("/domain")
async def get_domain_overview():
    """Get overview of the domain configuration."""
    domain_data = load_yaml_file(DOMAIN_FILE)
    
    return {
        "intents": domain_data.get('intents', []),
        "entities": domain_data.get('entities', []),
        "slots": list(domain_data.get('slots', {}).keys()),
        "responses": list(domain_data.get('responses', {}).keys()),
        "actions": domain_data.get('actions', []),
        "forms": list(domain_data.get('forms', {}).keys())
    }
