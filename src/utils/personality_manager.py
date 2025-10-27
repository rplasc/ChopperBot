import asyncio
from typing import Optional, Dict
from src.personalities import ChopperbotPersonality, personalities, custom_personalities
from src.moderation.logging import logger

class ServerPersonalityManager:
    def __init__(self):
        self.server_personalities: Dict[str, tuple[str, bool]] = {}
        # Format: {server_id: (personality_name_or_object, is_custom)}
        self._lock = asyncio.Lock()
        self._default = ("Default", False)
    
    async def get_personality(self, server_id: Optional[str]) -> ChopperbotPersonality:
        
        # DMs use default personality
        if server_id is None or server_id == "dm":
            return personalities["Default"]
        
        async with self._lock:
            personality_data = self.server_personalities.get(server_id, self._default)
            personality_name, is_custom = personality_data
            
            if is_custom:
                # Custom roleplay personality
                if isinstance(personality_name, ChopperbotPersonality):
                    return personality_name
                else:
                    return custom_personalities(personality_name)
            else:
                # Standard personality
                return personalities.get(personality_name, personalities["Default"])
    
    async def set_personality(self, server_id: str, personality_name: str) -> bool:
        
        if personality_name not in personalities:
            return False
        
        async with self._lock:
            self.server_personalities[server_id] = (personality_name, False)
            logger.info(f"Set personality for server {server_id}: {personality_name}")
            return True
    
    async def set_custom_personality(self, server_id: str, character: str):        
        async with self._lock:
            personality_obj = custom_personalities(character)
            self.server_personalities[server_id] = (personality_obj, True)
            logger.info(f"Set custom personality for server {server_id}: {character}")
    
    async def reset_personality(self, server_id: str):        
        async with self._lock:
            if server_id in self.server_personalities:
                del self.server_personalities[server_id]
                logger.info(f"Reset personality for server {server_id}")
    
    async def get_personality_name(self, server_id: str) -> str:        
        personality_data = self.server_personalities.get(server_id, self._default)
        personality_name, is_custom = personality_data
        
        if is_custom:
            if isinstance(personality_name, ChopperbotPersonality):
                return personality_name.name
            return f"Roleplay: {personality_name}"
        else:
            return personality_name
    
    def get_all_server_personalities(self) -> Dict[str, str]:        
        result = {}
        for server_id, (name, is_custom) in self.server_personalities.items():
            if is_custom:
                if isinstance(name, ChopperbotPersonality):
                    result[server_id] = name.name
                else:
                    result[server_id] = f"Roleplay: {name}"
            else:
                result[server_id] = name
        return result

# Global instance
personality_manager = ServerPersonalityManager()


# ============================================================================
# HELPER FUNCTIONS (for backward compatibility and ease of use)
# ============================================================================

async def get_server_personality(server_id: Optional[str]) -> ChopperbotPersonality:
    return await personality_manager.get_personality(server_id)

async def set_server_personality(server_id: str, personality_name: str) -> bool:
    return await personality_manager.set_personality(server_id, personality_name)

async def set_server_custom_personality(server_id: str, character: str):
    await personality_manager.set_custom_personality(server_id, character)

async def reset_server_personality(server_id: str):
    await personality_manager.reset_personality(server_id)

async def get_server_personality_name(server_id: str) -> str:
    return await personality_manager.get_personality_name(server_id)