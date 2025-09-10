import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Use MongoDB Atlas URI from environment variable
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not set in environment variables")

client = MongoClient(MONGO_URI)

# Database and collection
db = client["gchat_ai"]
messages_col = db["messages_history"]

def save_message(context_key, role, text):
    """
    Save a message and keep only the last 5 per conversation.
    
    context_key:
        - thread_name (for group chats)
        - space_id (for 1:1 DMs)
    role: 'user' or 'ai'
    """
    # Insert new message
    messages_col.insert_one({
        "thread_name": context_key,  # kept same field name in DB
        "role": role,
        "text": text
    })

    # Keep only last 5 messages per conversation
    all_msgs = list(messages_col.find({"thread_name": context_key}).sort("_id", -1))
    if len(all_msgs) > 5:
        ids_to_delete = [m["_id"] for m in all_msgs[5:]]
        messages_col.delete_many({"_id": {"$in": ids_to_delete}})

def get_last_messages(context_key, limit=5):
    """
    Fetch last N messages for a conversation (oldest first).
    
    context_key:
        - thread_name (for group chats)
        - space_id (for 1:1 DMs)
    """
    messages = list(
        messages_col.find({"thread_name": context_key})
        .sort("_id", -1)        # newest first
        .limit(limit)
    )
    return list(reversed(messages))  # oldest first
