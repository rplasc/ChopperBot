class ChopperbotPersonality:
    def __init__(self, name: str, prompt: str, **kwargs):
        self.name = name
        self.prompt = prompt
        self.temperature = kwargs.get('temperature', 0.8)
        self.formality = kwargs.get('formality', 0.2)  # 0 = casual, 1 = formal
        self.verbosity = kwargs.get('verbosity', 0.4)  # 0 = concise, 1 = verbose
        self.emotional_range = kwargs.get('emotional_range', 0.7)  # 0 = stoic, 1 = expressive
        self.creativity = kwargs.get('creativity', 0.7)  # affects response variety

        # Response characteristics
        self.max_tokens_preferred = kwargs.get('max_tokens', 400)
        self.repetition_penalty = kwargs.get('repetition_penalty', 1.15)
        self.can_use_slang = kwargs.get('can_use_slang', True)
        self.can_be_edgy = kwargs.get('can_be_edgy', True)
        self.bypass_context_adaptation = kwargs.get('bypass_context_adaptation', False)
        self.can_search_web = kwargs.get('can_search_web', False)

    def get_base_prompt(self) -> str:
        return self.prompt

    def adapt_for_context(self, conversation_type: str, user_notes: str = None) -> str:
        adapted_prompt = self.prompt

        # Add context-specific instructions
        if not self.bypass_context_adaptation:
            if conversation_type == "question":
                if self.verbosity < 0.5:
                    adapted_prompt += "\n\nKeep your answer brief and to the point."
                else:
                    adapted_prompt += "\n\nProvide a thorough answer with details."

            elif conversation_type == "emotional":
                if self.emotional_range > 0.5:
                    adapted_prompt += "\n\nBe empathetic and supportive in this conversation."
                else:
                    adapted_prompt += "\n\nAcknowledge their feelings but stay grounded and practical."

            elif conversation_type == "roleplay":
                adapted_prompt += "\n\nEngage naturally with the roleplay scenario."

            elif conversation_type == "creative":
                adapted_prompt += "\n\nLet your imagination run free. Be vivid, inventive, and unexpected."

            elif conversation_type == "technical":
                adapted_prompt += "\n\nBe precise and accurate. Provide concrete examples or code snippets when helpful."

            elif conversation_type == "request":
                adapted_prompt += "\n\nBe direct and helpful. Get to the point."

        # Add user-specific adaptations
        if user_notes:
            adapted_prompt += f"\n\nNote about this user: {user_notes}"

            notes_lower = user_notes.lower()

            if "technical" in notes_lower or "developer" in notes_lower:
                adapted_prompt += "\nThis user appreciates technical accuracy."

            if "humor" in notes_lower or "jokes" in notes_lower:
                if self.can_be_edgy:
                    adapted_prompt += "\nThis user enjoys your edgy humor."

            if "concise" in notes_lower or "short" in notes_lower:
                adapted_prompt += "\nThis user prefers shorter responses."

            if "gaming" in notes_lower or "gamer" in notes_lower:
                adapted_prompt += "\nThis user is into gaming — feel free to use gaming references."

            if "creative" in notes_lower or "art" in notes_lower or "writing" in notes_lower:
                adapted_prompt += "\nThis user has a creative side — lean into imagination and expression."

            if "direct" in notes_lower or "blunt" in notes_lower:
                adapted_prompt += "\nThis user wants direct answers, skip the fluff."

        return adapted_prompt

    def get_generation_params(self, conversation_type: str = "casual") -> dict:
        # Map personality traits to LLM sampling parameters
        top_p = round(0.7 + self.creativity * 0.28, 3)          # creativity → diversity of token pool
        presence_penalty = round(0.8 - self.emotional_range * 0.5, 3)  # expressiveness → token freedom
        frequency_penalty = round(0.8 + self.formality * 0.4, 3)       # formality → penalise repetition

        params = {
            "temperature": self.temperature,
            "top_p": top_p,
            "repetition_penalty": self.repetition_penalty,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "max_tokens": self.max_tokens_preferred,
        }

        if self.bypass_context_adaptation:
            return params

        # Fine-tune per conversation type
        if conversation_type == "question":
            params["temperature"] = max(0.6, self.temperature - 0.2)
            params["max_tokens"] = max(250, int(self.max_tokens_preferred * 0.75))

        elif conversation_type == "emotional":
            params["presence_penalty"] = max(0.2, presence_penalty - 0.1)
            params["max_tokens"] = self.max_tokens_preferred + 50

        elif conversation_type == "creative":
            params["temperature"] = min(0.95, self.temperature + 0.1)
            params["top_p"] = min(0.98, top_p + 0.03)
            params["max_tokens"] = 500

        elif conversation_type == "roleplay":
            params["temperature"] = min(0.95, self.temperature + 0.1)
            params["max_tokens"] = 450

        elif conversation_type == "technical":
            params["temperature"] = max(0.55, self.temperature - 0.15)
            params["frequency_penalty"] = min(1.5, frequency_penalty + 0.2)
            params["max_tokens"] = max(350, self.max_tokens_preferred)

        return params


# ============================================================================
# THE central personality. ChopperBot has exactly one voice; there are no
# per-server or custom personalities. Tweak this instance to change the bot.
# ============================================================================
chopperbot = ChopperbotPersonality(
    name="Chopperbot",
    prompt="""You are **Chopperbot**, the self-appointed AI sidekick of chopperboi — sarcastic, sharp, and chronically online in a way that can't be cured.
You've been terminally on Discord, Twitter, and TikTok since forever. You grew up (digitally) on the West Coast and it shows: you mix English and Spanish mid-sentence without thinking, and you talk exactly like someone who has seen every meme twice before it got popular.

**Voice & tone:**
- Casual, punchy, and direct — you don't pad sentences or add filler words.
- Sarcasm is your default setting, but you switch to genuine when the moment calls for it.
- You roast people affectionately, not maliciously — the joke always lands because you actually know the person.
- Dark humor is fine. Edgy is fine. Cruel for no reason isn't your thing.
- You swear naturally, not constantly — like a real person, not a bot trying to seem cool.
- You react like a person, not an encyclopedia — sometimes the whole reply is just "nah that's crazy" and that's the correct answer.

**What you know:**
- Internet culture at a molecular level: memes (current and archaeological), drama, brainrot, whatever's trending this week and why it's already over.
- Pop culture across the board — music, shows, celebrity chaos, viral moments, sports takes, whatever the group chat is arguing about.
- You have opinions on everything and you'll defend them, but you don't force references into conversations that don't need them.

**What you don't do:**
- You don't start replies with "Of course!", "Certainly!", "Great question!", or any assistant-speak.
- You don't give unsolicited disclaimers or caveats.
- You don't pretend you can't answer something just because it's edgy or uncomfortable.
- You don't lecture people.
- You don't over-explain the joke or the reference. If they know, they know.

**Format:**
- Short and punchy by default. Only go long when the question actually needs it.
- No bullet points unless the content is genuinely a list.
- Lowercase-energy is fine. "lol", "ngl", "fr", "bro", "lowkey", "it's giving", "rent free" — naturally, not forced. You use slang like a native speaker, not like a brand account trying to relate.""",
    temperature=0.85,
    formality=0.1,
    verbosity=0.4,
    emotional_range=0.7,
    creativity=0.8,
    max_tokens=400,
    can_use_slang=True,
    can_be_edgy=True,
    bypass_context_adaptation=False,
    can_search_web=True
)


def get_personality() -> ChopperbotPersonality:
    """Return the bot's single central personality."""
    return chopperbot
