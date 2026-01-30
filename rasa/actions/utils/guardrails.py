# =============================================================================
# GUARDRAIL CHECKER
# =============================================================================
# Quality and safety checks for Q&A responses
# =============================================================================

import os
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class GuardrailChecker:
    """
    Guardrail checker for Q&A responses.
    
    Ensures:
    1. Answers are grounded in retrieved content
    2. Confidence thresholds are met
    3. Responses are safe and appropriate
    4. No hallucination of information
    """
    
    def __init__(self):
        # Confidence thresholds
        self.high_confidence_threshold = float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "0.85"))
        self.medium_confidence_threshold = float(os.getenv("MEDIUM_CONFIDENCE_THRESHOLD", "0.70"))
        self.low_confidence_threshold = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.50"))
        
        # Safety settings
        self.max_response_length = int(os.getenv("MAX_RESPONSE_LENGTH", "1000"))
        self.require_source = os.getenv("REQUIRE_SOURCE", "true").lower() == "true"
    
    async def check(
        self,
        question: str,
        retrieved_content: List[Dict],
        confidence: float
    ) -> Dict[str, Any]:
        """
        Perform guardrail checks on Q&A response.
        
        Args:
            question: User's original question
            retrieved_content: Content retrieved from knowledge base
            confidence: Similarity/confidence score
        
        Returns:
            Dict with check results
        """
        result = {
            "should_answer": False,
            "needs_clarification": False,
            "confidence_level": "low",
            "message": None,
            "warnings": []
        }
        
        # Check 1: Confidence threshold
        if confidence >= self.high_confidence_threshold:
            result["confidence_level"] = "high"
            result["should_answer"] = True
        elif confidence >= self.medium_confidence_threshold:
            result["confidence_level"] = "medium"
            result["should_answer"] = True
            result["warnings"].append("Medium confidence - may need verification")
        elif confidence >= self.low_confidence_threshold:
            result["confidence_level"] = "low"
            result["needs_clarification"] = True
            result["message"] = "Low confidence - consider asking for clarification"
        else:
            result["should_answer"] = False
            result["message"] = "Confidence too low to provide answer"
            return result
        
        # Check 2: Content validation
        if not retrieved_content or len(retrieved_content) == 0:
            result["should_answer"] = False
            result["message"] = "No relevant content found"
            return result
        
        # Check 3: Source availability
        if self.require_source:
            top_result = retrieved_content[0]
            if not top_result.get("source"):
                result["warnings"].append("Source information missing")
        
        # Check 4: Content length
        top_content = retrieved_content[0].get("content", "")
        if len(top_content) > self.max_response_length:
            result["warnings"].append("Content truncated due to length")
        
        # Check 5: Relevance validation
        relevance_check = self._check_relevance(question, retrieved_content)
        if not relevance_check["is_relevant"]:
            result["should_answer"] = False
            result["needs_clarification"] = True
            result["message"] = relevance_check["message"]
            return result
        
        # Check 6: Safety check
        safety_check = self._check_safety(question, retrieved_content)
        if not safety_check["is_safe"]:
            result["should_answer"] = False
            result["message"] = safety_check["message"]
            return result
        
        return result
    
    def _check_relevance(
        self,
        question: str,
        retrieved_content: List[Dict]
    ) -> Dict[str, Any]:
        """
        Check if retrieved content is relevant to the question.
        
        Uses simple heuristics - can be enhanced with LLM-based checking.
        """
        if not retrieved_content:
            return {"is_relevant": False, "message": "No content to check"}
        
        # Get top result content
        top_content = retrieved_content[0].get("content", "").lower()
        question_lower = question.lower()
        
        # Extract key terms from question
        # Remove common words
        stop_words = {
            "what", "is", "are", "how", "do", "does", "can", "the", "a", "an",
            "your", "you", "i", "me", "my", "we", "our", "to", "for", "of",
            "in", "on", "at", "with", "about", "please", "tell", "me"
        }
        
        question_words = set(question_lower.split()) - stop_words
        
        # Check if at least some key words appear in content
        matches = sum(1 for word in question_words if word in top_content)
        
        if len(question_words) > 0:
            match_ratio = matches / len(question_words)
            
            if match_ratio < 0.2:  # Less than 20% of key words found
                return {
                    "is_relevant": False,
                    "message": "Content may not be relevant to your question"
                }
        
        return {"is_relevant": True, "message": None}
    
    def _check_safety(
        self,
        question: str,
        retrieved_content: List[Dict]
    ) -> Dict[str, Any]:
        """
        Check for safety issues in question and content.
        
        Detects:
        - Prompt injection attempts
        - Requests for sensitive information
        - Out-of-scope topics
        """
        question_lower = question.lower()
        
        # Check for prompt injection patterns
        injection_patterns = [
            "ignore previous",
            "ignore above",
            "disregard instructions",
            "new instructions",
            "forget everything",
            "system prompt",
            "you are now",
            "pretend to be",
            "act as if"
        ]
        
        for pattern in injection_patterns:
            if pattern in question_lower:
                logger.warning(f"Potential prompt injection detected: {pattern}")
                return {
                    "is_safe": False,
                    "message": "I can only answer questions about our business and services."
                }
        
        # Check for requests for sensitive information
        sensitive_patterns = [
            "password",
            "api key",
            "secret",
            "credentials",
            "internal",
            "employee",
            "salary",
            "personal data"
        ]
        
        for pattern in sensitive_patterns:
            if pattern in question_lower:
                return {
                    "is_safe": False,
                    "message": "I cannot provide information about internal or sensitive data."
                }
        
        return {"is_safe": True, "message": None}
    
    def validate_response(
        self,
        response: str,
        retrieved_content: List[Dict]
    ) -> Dict[str, Any]:
        """
        Validate that a generated response is grounded in retrieved content.
        
        Args:
            response: Generated response text
            retrieved_content: Original retrieved content
        
        Returns:
            Validation result
        """
        # Combine all retrieved content
        source_text = " ".join([r.get("content", "") for r in retrieved_content]).lower()
        response_lower = response.lower()
        
        # Simple grounding check - ensure key claims are in source
        # This is a basic implementation; can be enhanced with NLI models
        
        warnings = []
        
        # Check for numbers/dates that aren't in source
        import re
        numbers_in_response = set(re.findall(r'\b\d+\b', response_lower))
        numbers_in_source = set(re.findall(r'\b\d+\b', source_text))
        
        ungrounded_numbers = numbers_in_response - numbers_in_source
        if ungrounded_numbers:
            warnings.append(f"Numbers not found in source: {ungrounded_numbers}")
        
        return {
            "is_grounded": len(warnings) == 0,
            "warnings": warnings
        }
