import random

ALIASES = [
    "Shadow", "Nightfox", "Redhand", "Ghostwalker", "Slip", "Viper"
    "The Coyote", "Blacktop", "Knuckles", "Silk", "Midas", "Sable"
    "Wraith", "Phantom", "Blade", "Raven", "Specter", "Storm"
    "Echo", "Thunder", "Frost", "Ash", "Flare", "Ember"
    "Fury", "Vortex", "Tempest", "Tornado", "Typhoon", "Whirlwind"
]
CRIMES = [
    "petty theft", "grand larceny", "smuggling",
    "heist planning", "forged documents", "con art",
    "illegal street racing", "hacking", "burglary",
    "smash-and-grab", "bootlegging", "counterfeiting"
]
BADGES = ["Most Wanted", "Bounty Hunter's Target", "Undercover Interest", "Wanted (Low Risk)", "High-Profile"]
WEAPONS = ["none", "stolen motorbike", "custom lockpick set", "old revolver (prop)", "sawed-off (prop)"]
LOCATIONS = [
    "New York City", "Tokyo", "Paris", "Rio de Janeiro", "Dubai", "Los Angeles", "Chicago", "Miami"
    "Boston", "Washington D.C.", "Santa Maria", "Merced", "Guadalupe", "Peter's House", "Fresno"
]
STATUSES = ["At large", "In hiding", "Recently spotted", "Captured (escaped)", "Unknown"]

def format_money(n):
    return f"${n:,}"

# Helper to build a fake record
def build_fake_record(target_name: str):
    aliases = random.sample(ALIASES, k=random.randint(1, 3))
    primary_alias = random.choice(aliases)
    crimes = random.sample(CRIMES, k=random.randint(1, 3))
    age = random.randint(18, 65)
    bounty = random.randint(100, 50000) * random.choice([1, 10, 50])
    last_known = random.choice(LOCATIONS)
    status = random.choice(STATUSES)
    badge = random.choice(BADGES)
    weapon = random.choice(WEAPONS)
    return {
        "target_name": target_name,
        "primary_alias": primary_alias,
        "aliases": aliases,
        "crimes": crimes,
        "age": age,
        "bounty": bounty,
        "last_known": last_known,
        "status": status,
        "badge": badge,
        "weapon": weapon
    }
