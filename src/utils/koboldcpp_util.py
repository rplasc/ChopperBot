import re
from src.services.llm_service import chat_completion

async def get_kobold_response(messages):
    # Legacy name kept for compatibility; routes through the provider-agnostic
    # LLM service (KoboldCPP, Ollama, LM Studio, or OpenAI via env config).
    return await chat_completion(messages, {"max_tokens": 512})
        
def sanitize_bot_output(text: str, bot_name: str = "Chopperbot") -> str:
    # Keep only the assistant's first reply before it starts imitating others
    first_line = re.split(r"\n(?:Me|User|You):", text, flags=re.IGNORECASE)[0]
    # Strip its own prefix if present
    first_line = re.sub(rf"^{bot_name}:\s*", "", first_line, flags=re.IGNORECASE).strip()
    return first_line