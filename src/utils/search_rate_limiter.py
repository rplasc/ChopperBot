import re
from datetime import datetime, timedelta

class SearchRateLimiter:
    def __init__(self, searches_per_hour: int = 3):
        self.searches_per_hour = searches_per_hour
        self.search_history = {}
    
    def can_search(self, channel_key: str) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(hours=1)
        
        if channel_key not in self.search_history:
            self.search_history[channel_key] = []
        
        # Remove old timestamps
        self.search_history[channel_key] = [
            ts for ts in self.search_history[channel_key] 
            if ts > cutoff
        ]
        
        # Check if under limit
        return len(self.search_history[channel_key]) < self.searches_per_hour
    
    def record_search(self, channel_key: str):
        if channel_key not in self.search_history:
            self.search_history[channel_key] = []
        self.search_history[channel_key].append(datetime.now())

# Global rate limiter
search_limiter = SearchRateLimiter(searches_per_hour=10)

def sanitize_message_for_search(content: str) -> str:

    # Remove username prefix pattern: "username: <@user_id> message"
    content = re.sub(r'^[\w\s]+:\s*', '', content)
    
    # Remove user mentions: <@123456789> or <@!123456789>
    content = re.sub(r'<@!?\d+>', '', content)
    
    # Remove role mentions: <@&123456789>
    content = re.sub(r'<@&\d+>', '', content)
    
    # Remove channel mentions: <#123456789>
    content = re.sub(r'<#\d+>', '', content)
    
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    
    return content

def should_trigger_web_search(content: str, channel_key: str) -> bool:

    # Check rate limit first
    if not search_limiter.can_search(channel_key):
        return False
    
    content_lower = content.lower()
    
    # 1. EXPLICIT SEARCH KEYWORDS
    explicit_search_terms = [
        "search for", "look up", "find information about",
        "what's happening", "latest news", "recent news",
        "current events", "breaking news"
    ]
    if any(term in content_lower for term in explicit_search_terms):
        return True
    
    # 2. TIME-SENSITIVE INDICATORS
    time_indicators = [
        "today", "this week", "this month", "right now",
        "currently", "recent", "latest", "new"
    ]
    
    # 3. DATE REFERENCES (2024, 2025, specific months)
    date_pattern = r'\b(202[4-5]|january|february|march|april|may|june|july|august|september|october|november|december)\b'
    has_date = bool(re.search(date_pattern, content_lower))
    
    # 4. CURRENT EVENT TOPICS (sports scores, elections, weather, stock prices)
    current_event_keywords = [
        "score", "election", "weather forecast", "stock price",
        "who won", "who's winning", "game result"
    ]
    
    # Require BOTH a question AND a time/currency indicator
    is_question = "?" in content or any(q in content_lower for q in ["what", "who", "when", "how"])
    has_time_signal = any(indicator in content_lower for indicator in time_indicators)
    has_current_topic = any(keyword in content_lower for keyword in current_event_keywords)
    
    # Only trigger if we have strong signals
    if is_question and (has_date or has_current_topic):
        return True
    
    if is_question and has_time_signal and len(content.split()) >= 6:
        return True
    
    return False


# ALTERNATIVE: Uses a whitelist approach for even stricter control
#TODO: Further testing needed
SEARCH_WHITELIST_PATTERNS = [
    r'what.*(?:happen|news|latest).*today',
    r'current.*(?:price|score|weather)',
    r'who won.*(?:election|game|match)',
    r'(?:news|updates?).*(?:202[4-5]|today|this week)',
    r'latest.*(?:version|release|update)',
]

def should_trigger_web_search_whitelist(content: str, channel_key: str) -> bool:

    if not search_limiter.can_search(channel_key):
        return False
    
    content_lower = content.lower()
    
    for pattern in SEARCH_WHITELIST_PATTERNS:
        if re.search(pattern, content_lower):
            return True
    
    return False
