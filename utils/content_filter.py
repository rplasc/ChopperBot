# Read and store curse words in a set
curse_words = set()
with open('utils/profanity_list.txt', 'r') as f:
    curse_words = {line.strip() for line in f}

def censor_curse_words(message_content):
    censor_symbol = "*"

    for curse_word in curse_words:
        message_content = message_content.replace(curse_word, censor_symbol * len(curse_word))

    return message_content
