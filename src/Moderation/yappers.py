import json
import os
import discord

def load_yaps():
    try:
        script_dir = os.path.dirname(__file__)
        filepath = os.path.join(script_dir, 'yappers_data.json')
        with open(filepath, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_yaps(message_counts):
    script_dir = os.path.dirname(__file__)
    filepath = os.path.join(script_dir, 'yappers_data.json')
    with open(filepath, 'w') as file:
        json.dump(message_counts, file)