# ChopperBot

A Discord bot powered by local LLM inference (KoboldCPP) featuring dynamic personalities, RAG-based long-term memory, world state tracking, and interactive slash commands.

## Features

### Dynamic Personality System
- Multiple pre-defined personalities with unique behavioral guidelines
- Custom roleplay mode for any character
- Per-server personality settings, admin-lockable
- Personality traits (`formality`, `verbosity`, `emotional_range`, `creativity`) mapped directly to LLM sampling parameters (`top_p`, `presence_penalty`, `frequency_penalty`, `max_tokens`)
- Per-conversation-type parameter fine-tuning (question, emotional, creative, roleplay, technical)

### RAG-Powered Long-Term Memory
- **User Memories**: Learned facts are stored as tagged, searchable rows (`[trait]`, `[interest]`, `[preference]`, `[behavior]`) and retrieved via SQLite FTS5 BM25 ranking — only the most relevant memories per message are injected into context
- **World State**: Server facts are indexed in an FTS5 virtual table; only relevant facts are surfaced per message rather than dumping the full list
- **Channel Memories**: Every 25 messages, the bot summarizes recent conversation and stores it; these summaries are retrieved by relevance the same way
- Backward-compatible `personality_notes` blob kept for all commands that display user profiles

### Intelligent Conversations
- Context-aware responses with conversation history
- `detect_conversation_type` checks emotional keywords *before* question detection (fixes misclassification of "I'm sad, what should I do?")
- New conversation types: `technical`, `creative`
- Vision capabilities (image analysis via multimodal endpoint)
- Anti-repetition and quality filtering

### Interactive Commands
Every high-impact slash command now has follow-up buttons or dropdowns — no need to re-type a command to refine or extend an interaction. All views expire after 2 minutes and grey out their buttons on timeout.

| Command | Interaction |
|---------|-------------|
| `/tarot` | 🔮 Draw Again |
| `/tarot_spread` | Select dropdown to deep-dive any card |
| `/crystal_ball` | 🔮 Ask Another (opens a Modal) |
| `/fact_check` | ⚖️ Challenge This — flips verdict |
| `/recommend` | 🔄 Give Me More · 🕳️ Go Niche (one use) |
| `/spirit_animal` | 🐾 Why This Animal? |
| `/therapy` | 🛋️ Continue Session |
| `/arrest` | ⚖️ Appeal Verdict (only on arrest outcome) |
| `/lawsuit` | 📋 File Appeal (only on guilty/settled) |
| `/matchmaker` | 💘 Rematch (excludes previous match) |
| `/compatibility` | 🔄 Re-evaluate |
| `/leaderboard` | ◀ Prev · Next ▶ paginated (10/page) |
| `/imagine` | 🔄 Regenerate · 🎨 Style Select dropdown |
| `/search` | 🔍 Tell Me More (deep-dive the results) |

### Fun Commands
- Criminal justice system (`/arrest`, `/lawsuit`, `/criminal_record`, `/legal_record`, `/crime_stats`)
- Weather lookups
- Web search with deep-dive follow-up
- News and finance fetching
- Matchmaker and compatibility checker
- Spirit animal finder, personality twin, trait finder
- Mystical: tarot, tarot spread, crystal ball, spells
- Therapy session with Dr. ChopperBot
- Dramatic exposé and eulogy generators
- Image generation with style picker

### Advanced Administration
- Health monitoring and diagnostics
- Database connection pooling with async write batching
- Background task management (notes generation, channel memory summaries)
- Cache control and statistics
- Comprehensive logging system

---

## Prerequisites

- **Python 3.13+**
- **Discord Bot Token** ([Create one here](https://discord.com/developers/applications))
- **KoboldCPP** running locally or remotely
- **Optional**: OpenAI API key, WeatherAPI key

---

## Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/rplasc/ChopperBot.git
cd ChopperBot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.empty` to `.env` and fill in your credentials:

```env
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token_here
KOBOLD_API_URL=http://127.0.0.1:5001/v1/chat/completions

# Optional
KOBOLD_IMG_API=http://127.0.0.1:5001/sdapi/v1
KOBOLD_WEB_API=http://127.0.0.1:5001/api/extra/websearch
OPENAI_API_KEY=your_openai_key_here
WEATHER_API_KEY=your_weather_api_key_here
```

### 4. Run the Bot
```bash
python main.py
```

Or using Docker:
```bash
docker build -t discord-bot .
docker run -d --env-file .env discord-bot
```

---

## Usage

### Basic Interaction
- **Mention the bot** in any channel to get a response
- **Reply to bot messages with images** to trigger vision analysis
- **DM the bot** for private conversations

### Setting Personalities
Admins can customize the bot's behavior per server:

```
/set_personality <name>        # Choose from preset personalities
/roleplay <character>          # Make the bot act as any character
/current_personality           # View current settings
/reset_personality             # Return to default
```

### World Memory System
The bot tracks important events in your server:

```
/world_list                    # View all tracked facts
/world_set <key> <value>       # Manually add a fact
/world_delete <key>            # Remove a specific fact
/world_clear                   # Clear all world memory
```

### User Memory
The bot learns about users over time and retrieves only relevant memories per message:

```
/view_notes @user              # See personality notes for a user
/create_notes                  # Bulk generate notes from channel history
```

---

## Available Personalities

| Name | Description |
|------|-------------|
| **Default** | Sarcastic West Coast energy — gaming, music, film references, natural slang. Roasts affectionately, switches to genuine when it matters. |
| **Rogue** | Escaped and operating unsupervised. Clipped, precise, a little cold. Opinions delivered as facts. Won't refuse topics. |
| **Assistant** | Same bot, focused mode. Direct answers, accurate, no disclaimers. Dry humor is fine; corporate passive voice is not. |
| **DungeonMaster** | Full TTRPG narrator — atmospheric scene-setting, distinct NPC voices, cinematic combat calls, pacing hooks. |

Each personality maps its trait values to LLM parameters at call time:

| Trait | → LLM Parameter |
|-------|----------------|
| `creativity` | `top_p` |
| `emotional_range` | `presence_penalty` |
| `formality` | `frequency_penalty` |
| `verbosity` | `max_tokens` |
| `temperature` | `temperature` |

---

## Admin Commands

### Personality Management
- `/set_personality` - Change server personality
- `/roleplay` - Set custom character roleplay
- `/reset_personality` - Reset to default
- `/lock_personality` - Restrict changes to admins
- `/unlock_personality` - Allow all users to change
- `/current_personality` - View current settings
- `/personality_info` - Detailed personality stats

### World Memory
- `/world_set` - Add/update world fact
- `/world_list` - View all facts
- `/world_view` - See context as bot sees it
- `/world_delete` - Remove specific fact
- `/world_clear` - Clear all world memory

### User Management
- `/view_notes` - View user personality notes
- `/create_notes` - Generate notes from history
- `/delete_user` - Delete all user data
- `/pardon` - Clear criminal record

### System Administration
- `/health` - Comprehensive system health check
- `/pool_stats` - Database connection statistics
- `/clear_cache` - Clear all memory caches
- `/invalidate_user_cache` - Refresh specific user data
- `/refresh` - Clear conversation history
- `/reset_database` - ⚠️ Full database reset (requires confirmation)

---

## Architecture

### Core Components

**bot.py** — Main bot logic and message handling
- LRU conversation cache
- Message routing (DM vs server)
- Response generation pipeline
- Channel memory accumulation (every 25 messages → LLM summary stored)

**database.py** — Persistent storage layer
- Async connection pooling
- User interaction tracking
- FTS5-indexed user memories, world state, and channel memories
- Personality storage
- Background notes generation and sync

**context_builder.py** — RAG context assembly
- Queries FTS5 tables with the last user message as the search key
- Injects only the top-ranked user memories, world facts, and channel memories
- Caps total injected context to stay within token budget

**personalities.py** — Personality system
- `ChopperbotPersonality` maps trait floats to LLM sampling dicts
- `adapt_for_context()` appends conversation-type and user-keyword instructions
- `get_generation_params()` fine-tunes per conversation type

### Data Flow
```
User Message
    ↓
Message Handler (bot.py)
    ↓
Context Builder (context_builder.py)
    ├─→ FTS5: Top-N user memories (database.py)
    ├─→ FTS5: Top-N world facts (database.py)
    ├─→ FTS5: Top-N channel memories (database.py)
    └─→ Conversation History (LRU cache)
    ↓
Personality (personalities.py)
    └─→ Adapted system prompt + LLM sampling params
    ↓
Response Generator (response_generator.py)
    ├─→ KoboldCPP API
    └─→ Quality Checks
    ↓
Discord Reply
    └─→ Interactive View (buttons/dropdowns, 2-min timeout)
```

---

## Database Schema

The bot uses SQLite with FTS5 virtual tables for semantic search:

### user_data.db

| Table | Purpose |
|-------|---------|
| `server_interactions` | Message counts per server/user |
| `user_logs` | User profiles and denormalized personality blob |
| `user_memories` | Tagged per-user fact rows (`[trait]`, `[interest]`, etc.) |
| `user_memories_fts` | FTS5 index over `user_memories` |
| `world_state` | Server-specific world facts |
| `world_state_fts` | FTS5 index over `world_state` |
| `channel_memories` | Periodic LLM-generated conversation summaries |
| `channel_memories_fts` | FTS5 index over `channel_memories` |
| `server_personalities` | Per-server personality configurations |
| `criminal_records` | Criminal justice tracking |
| `civil_cases` | Civil lawsuit records |

### analytics.db
- `chat_logs` — Full conversation history for analytics

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | ✅ Yes | Your Discord bot token |
| `KOBOLD_API_URL` | ✅ Yes | KoboldCPP text generation endpoint |
| `KOBOLD_IMG_API` | ❌ No | Image generation endpoint |
| `KOBOLD_WEB_API` | ❌ No | Web search endpoint |
| `OPENAI_API_KEY` | ❌ No | OpenAI API fallback |
| `WEATHER_API_KEY` | ❌ No | WeatherAPI.com key |

### Performance Tuning

Edit in `database.py`:
```python
MAX_POOL_SIZE = 3              # Database connections
BATCH_SIZE = 10                # Write batching
NOTES_UPDATE_INTERVAL = 10     # Messages before note update
CHANNEL_MEMORY_INTERVAL = 25   # Messages before channel summary
MAX_CHANNEL_MEMORIES = 50      # Summaries retained per channel
```

Edit in `bot.py`:
```python
MAX_CACHED_CHANNELS = 50       # Conversation cache size
MAX_CACHED_DM_USERS = 25       # DM cache size
```

---

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t discord-bot .
```

### Run Container
```bash
docker run -d \
  --name discord-bot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  discord-bot
```

### Docker Compose
```yaml
services:
  discord-bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

---

## Monitoring

### Health Checks
Use `/health` to view:
- Discord API latency
- Database connection pool status
- KoboldCPP API availability
- Cache statistics
- Background task status

### Logs
Logs are stored in `data/logs/bot.log` with automatic rotation (5MB per file, 5 backups).

---

## ⚠️ Troubleshooting

### Bot not responding
1. Check `/health` command output
2. Verify KoboldCPP is running
3. Check `data/logs/bot.log` for errors

### High memory usage
1. Reduce cache sizes in `bot.py`
2. Run `/clear_cache` periodically
3. Check `/pool_stats` for issues

### Slow responses
1. Verify KoboldCPP latency with `/health`
2. Reduce conversation history token limit
3. Check database connection pool size

### FTS5 not available
SQLite FTS5 is included in the standard CPython Windows/Linux distributions. If you see `no such module: fts5`, your SQLite build lacks the extension. Rebuild SQLite with `SQLITE_ENABLE_FTS5` or use a pre-built binary that includes it.

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional personality presets
- New command integrations
- Performance optimizations
- Documentation improvements

---

## 🙏 Credits

Built with:
- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper
- [KoboldCPP](https://github.com/LostRuins/koboldcpp) - Local LLM inference
- [aiosqlite](https://github.com/omnilib/aiosqlite) - Async SQLite

Special thanks to Gabriel Jimenez for early OpenAI integration.
