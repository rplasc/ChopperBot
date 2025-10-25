# Read and store curse words in a set
curse_words = set()
with open('src/utils/profanity_list.txt', 'r') as f:
    curse_words = {line.strip() for line in f}

# Read and store controversial figures in a set
controversial_figures = set()
with open('src/utils/controversial_figures.txt', 'r') as f:
    controversial_figures = {line.strip() for line in f}

def censor_curse_words(message_content):
    censor_symbol = "*"

    for curse_word in curse_words:
        message_content = message_content.replace(curse_word, censor_symbol * len(curse_word))

    return message_content

def filter_controversial(personality):
    # Check for exact match first (case-insensitive)
    if personality.lower() in [fig.lower() for fig in controversial_figures]:
        return False
    
    # Remove spaces from the personality for comparison
    personality_no_spaces = personality.replace(" ", "")
    return personality_no_spaces.lower() not in [fig.lower().replace(" ", "") for fig in controversial_figures]
