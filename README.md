# ChopperBot

A sophisticated Discord bot powered by local LLM inference (KoboldCPP) featuring dynamic personalities, long-term user memory, world state tracking, and advanced conversation capabilities.

## Features

### Dynamic Personality System
- Multiple pre-defined personalities with unique traits
- Custom roleplay mode for any character
- Per-server personality settings
- Temperature, formality, and creativity controls
- Admin-lockable personality settings

### Long-Term Memory
- **User Notes**: Automatically learns about users from conversations
- **World Memory**: Tracks ongoing events, relationships, and story elements (Currently undergoing an overhaul)
- Cached interactions for performance optimization
- Periodic memory updates based on conversation context

### Intelligent Conversations
- Context-aware responses with conversation history
- Vision capabilities (image analysis)
- Adaptive response quality based on conversation type
- Anti-repetition and quality filtering

### Fun Features
- Criminal justice system (arrest, sue, view records)
- Weather lookups
- Web search integration
- News fetching
- Relationship analyzer
- Meme generation
- Finance tracking

### Advanced Administration
- Health monitoring and diagnostics
- Database connection pooling
- Background task management
- Cache control and statistics
- Comprehensive logging system

---

## 📋 Prerequisites

- **Python 3.13+**
- **Discord Bot Token** ([Create one here](https://discord.com/developers/applications))
- **KoboldCPP** running locally or remotely
- **Optional**: OpenAI API key, WeatherAPI key

---

## 🚀 Quick Start

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

## 🎮 Usage

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
The bot automatically tracks important events in your server:

```
/world_list                    # View all tracked facts
/world_set <key> <value>       # Manually add a fact
/world_delete <key>            # Remove a specific fact
/world_clear                   # Clear all world memory
```

### User Memory
The bot learns about users over time:

```
/view_notes @user              # See personality notes for a user
/create_notes                  # Bulk generate notes from channel history
```

---

## 🎭 Available Personalities

The bot comes with several preset personalities, each with unique characteristics:

- **Default**: Sarcastic, but friendly assistant
- **Rogue**: Mean, bold, and unfiltered
- **Assistant**: Cold, unapologetic, and never afraid to answer any type of question
- **DungeonMaster**: Made for storytelling

Each personality has customizable parameters:
- Temperature (randomness)
- Formality level
- Verbosity
- Emotional range
- Creativity
- Token limits

---

## 🛠️ Admin Commands

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

## 🏗️ Architecture

### Core Components

**bot.py** - Main bot logic and message handling
- LRU conversation cache
- Message routing (DM vs server)
- Response generation pipeline

**database.py** - Persistent storage layer
- Connection pooling for performance
- User interaction tracking
- World state management
- Personality storage

**aclient.py** - Discord client configuration
- Intent management
- API credential storage

**personality_manager.py** - Personality system
- Multi-server personality tracking
- Dynamic prompt generation
- Custom character support

### Data Flow
```
User Message
    ↓
Message Handler (bot.py)
    ↓
Context Builder (context_builder.py)
    ├─→ User Notes (database.py)
    ├─→ World State (database.py)
    └─→ Conversation History (cache)
    ↓
Response Generator (response_generator.py)
    ├─→ KoboldCPP API
    └─→ Quality Checks
    ↓
Discord Reply
```

---

## 📊 Database Schema

The bot maintains several SQLite databases:

### user_data.db
- `server_interactions` - Message counts per server
- `user_logs` - User profiles and personality notes
- `world_state` - Server-specific world facts
- `server_personalities` - Personality configurations
- `criminal_records` - Fun criminal justice tracking
- `civil_cases` - Civil lawsuit records

### analytics.db
- `chat_logs` - Full conversation history for analytics

---

## 🔧 Configuration

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

Edit these constants in `database.py`:
```python
MAX_POOL_SIZE = 3              # Database connections
BATCH_SIZE = 10                # Write batching
NOTES_UPDATE_INTERVAL = 10     # Messages before note update
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

## 🔍 Monitoring

### Health Checks
Use `/health` command to view:
- Discord API latency
- Database connection pool status
- KoboldCPP API availability
- Cache statistics
- Background task status

### Logs
Logs are stored in `data/logs/bot.log` with automatic rotation (5MB per file, 5 backups).

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional personality presets
- New command integrations
- Performance optimizations
- Documentation improvements

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

---

## 🙏 Credits

Built with:
- [discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper
- [KoboldCPP](https://github.com/LostRuins/koboldcpp) - Local LLM inference
- [aiosqlite](https://github.com/omnilib/aiosqlite) - Async SQLite

Special thanks to Gabriel Jimenez for early OpenAI integration.