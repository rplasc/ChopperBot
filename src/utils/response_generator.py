import aiohttp
import re
from typing import List, Dict, Optional
from src.utils.personality_manager import get_server_personality
from src.utils.websearch_util import perform_web_search, format_results_for_prompt
from src.utils.search_rate_limiter import should_trigger_web_search, sanitize_message_for_search, search_limiter
from src.aclient import client
from src.moderation.logging import logger

def detect_conversation_type(content: str) -> str:
    content_lower = content.lower()
    
    # Question detection
    if "?" in content or any(q in content_lower for q in ["what", "how", "why", "who", "when", "where", "explain"]):
        return "question"
    
    # Emotional/Support detection
    if any(word in content_lower for word in ["sad", "happy", "angry", "worried", "excited", "scared", "depressed", "anxious"]):
        return "emotional"
    
    # Roleplay detection
    if "*" in content or content.startswith("*") or content.count("*") >= 2:
        return "roleplay"
    
    # Request detection
    if any(word in content_lower for word in ["please", "can you", "could you", "would you", "help me"]):
        return "request"
    
    return "casual"

def check_response_quality(response: str) -> tuple[bool, Optional[str]]:
    if not response or not response.strip():
        return False, "Empty response"
    
    # Too short (but allow short casual responses)
    if len(response.strip()) < 5:
        return False, "Response too short"
    
    # Repetitive characters
    if re.search(r'(.)\1{15,}', response):
        return False, "Repetitive characters detected"
    
    # Error indicators from model
    error_indicators = ["<|", "|>", "[ERROR]", "undefined", "<unk>"]
    if any(indicator in response for indicator in error_indicators):
        return False, "Response contains error indicators"
    
    # Incomplete thoughts (very long responses that end abruptly)
    if len(response.strip()) > 150:
        last_char = response.strip()[-1]
        if last_char not in ".!?…" and not response.endswith("*"):
            # Could be incomplete, but allow if last word seems complete
            words = response.strip().split()
            if words and len(words[-1]) < 3:
                return False, "Incomplete response"
    
    return True, None

async def generate_response(
    messages: List[Dict],
    conversation_type: str,
    server_id: Optional[str] = None,
    max_retries: int = 2
) -> str:
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Get personality-specific parameters
            personality = await get_server_personality(server_id)
            params = personality.get_generation_params(conversation_type)
            
            # Adjust temperature slightly on retries to get different output
            if attempt > 0:
                params["temperature"] = min(0.95, params["temperature"] + (attempt * 0.1))
                logger.debug(f"Retry {attempt + 1} with temperature {params['temperature']}")
            
            # Generate response
            response = await _call_kobold_api(messages, params)
            
            # Quality check
            is_valid, error = check_response_quality(response)
            
            if is_valid:
                return response
            
            # Log quality issue and retry
            logger.warning(f"Response quality issue (attempt {attempt + 1}/{max_retries}): {error}")
            last_error = error
            
        except Exception as e:
            logger.error(f"Error generating response (attempt {attempt + 1}/{max_retries}): {e}")
            last_error = str(e)
            
            if attempt == max_retries - 1:
                raise
    
    # All retries failed
    logger.error(f"All retries failed. Last error: {last_error}")
    return "I'm having trouble forming a response right now. Could you try rephrasing that?"

async def _call_kobold_api(messages: List[Dict], params: Dict) -> str:
    url = client.kobold_text_api
    
    # Build full payload
    payload = {
        "messages": messages,
        "temperature": params.get("temperature", 0.8),
        "top_p": 0.9,
        "top_k": 50,
        "frequency_penalty": 1.0,
        "presence_penalty": 0.6,
        "repetition_penalty": params.get("repetition_penalty", 1.15),
        "max_tokens": params.get("max_tokens", 400),
        "stop": ["\nUser:", "\nSystem:", "\nAssistant:", "\n\n\n"]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API error {resp.status}: {error_text}")
            
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

# ============================================================================
# COMMAND-SPECIFIC GENERATION (for crystal ball, news, etc.)
# ============================================================================

async def generate_command_response(
    prompt: str,
    server_id: Optional[str] = None,
    use_personality: bool = True,
    temperature: float = 0.9,
    max_tokens: int = 300,
    custom_params: dict = None
) -> str:    
    messages = []
    
    # Optionally include personality for consistent voice
    if use_personality:
        personality = await get_server_personality(server_id)
        if personality:
            # Use base personality without context adaptation
            system_prompt = personality.get_base_prompt()
            messages.append({"role": "system", "content": system_prompt})
    
    # Add the command prompt
    messages.append({"role": "user", "content": prompt})
    
    # Build parameters
    params = {
        "temperature": temperature,
        "repetition_penalty": 1.1,  # Lower for more creative commands
        "max_tokens": max_tokens
    }
    
    # Apply custom overrides
    if custom_params:
        params.update(custom_params)
    
    # Generate without quality checks (commands are one-off)
    return await _call_kobold_api(messages, params)

async def generate_roleplay_response(
    character_description: str,
    scenario: str,
    temperature: float = 0.95,
    max_tokens: int = 400
) -> str:
    messages = [
        {"role": "system", "content": character_description},
        {"role": "user", "content": scenario}
    ]
    
    params = {
        "temperature": temperature,
        "repetition_penalty": 1.05,  # Very low for roleplay creativity
        "max_tokens": max_tokens
    }
    
    return await _call_kobold_api(messages, params)

def sanitize_response(response: str, bot_name: str = "Chopperbot") -> str:

    # Keep only the first reply before bot starts imitating others
    first_line = re.split(r"\n(?:Me|User|You):", response, flags=re.IGNORECASE)[0]
    
    # Step 1: Remove any markdown formatting around bot name at the start
    first_line = re.sub(
        rf"^[\*_\[\]]*\s*{bot_name}\s*[\*_\[\]]*\s*[:\-]\s*",
        "",
        first_line,
        flags=re.IGNORECASE
    ).strip()
    
    # Step 2: Handle case where markdown remains after name removal
    first_line = re.sub(r"^[\*_]{1,3}\s*", "", first_line)
    
    # Step 3: Remove any orphaned colons or dashes at the start
    first_line = re.sub(r"^[:\-\s]+", "", first_line)
    
    # Step 4: Clean up trailing markdown
    first_line = re.sub(r"\s*[\*_]{1,3}$", "", first_line)
    
    # Step 5: Remove multiple consecutive newlines
    first_line = re.sub(r'\n{3,}', '\n\n', first_line)
    
    return first_line.strip()

# Response variety tracking
class ResponseTracker:
    def __init__(self, max_history: int = 50):
        self.history = {}  # {channel_key: [recent_responses]}
        self.max_history = max_history
    
    def add_response(self, channel_key: str, response: str):
        if channel_key not in self.history:
            self.history[channel_key] = []
        
        self.history[channel_key].append(response.lower())
        
        # Trim history
        if len(self.history[channel_key]) > self.max_history:
            self.history[channel_key] = self.history[channel_key][-self.max_history:]
    
    def is_repetitive(self, channel_key: str, response: str, threshold: float = 0.7) -> bool:
        if channel_key not in self.history or len(self.history[channel_key]) == 0:
            return False
        
        response_lower = response.lower()
        recent = self.history[channel_key][-5:]  # Check last 5
        
        for cached in recent:
            similarity = self._word_overlap_similarity(response_lower, cached)
            if similarity > threshold:
                return True
        
        return False
    
    def _word_overlap_similarity(self, str1: str, str2: str) -> float:
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0

# Global tracker instance
response_tracker = ResponseTracker()

async def generate_and_track_response(
    messages: List[Dict],
    conversation_type: str,
    channel_key: str,
    server_id: Optional[str] = None
) -> str:
    personality = await get_server_personality(server_id)

    if getattr(personality, "can_search_web", False):
        user_message = messages[-1]["content"] if messages else ""

        if should_trigger_web_search(user_message, channel_key):
            clean_query = sanitize_message_for_search(user_message)
            logger.info(f"Web search triggered: '{clean_query}'")
            try:
                results = await perform_web_search(clean_query)
                if results:
                    snippets = format_results_for_prompt(results)
                    messages.append({
                        "role": "system",
                        "content": f"Web search results:\n{snippets}\nUse these results to answer accurately."
                    })
                    search_limiter.record_search(channel_key)
            except Exception as e:
                logger.error(f"Search failed: {e}")

    response = await generate_response(messages, conversation_type, server_id)
    
    # Check if response is repetitive
    if response_tracker.is_repetitive(channel_key, response):
        logger.warning(f"Repetitive response detected in {channel_key}, regenerating...")

        # Try one more time with higher temperature
        params = personality.get_generation_params(conversation_type)
        params["temperature"] = min(0.95, params["temperature"] + 0.15)
        response = await _call_kobold_api(messages, params)
    
    # Track this response
    response_tracker.add_response(channel_key, response)
    
    return response
