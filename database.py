import os
import json

USER_DB_FILE = "users_memory.json"
WATCH_DB_FILE = "watchlist.json"
SETTINGS_DB_FILE = "settings.json"
PREDICT_DB_FILE = "predictions.json"

def load_db(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_db(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)
