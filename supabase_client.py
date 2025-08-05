import streamlit as st
import pandas as pd
import json
from supabase import Client

# Import constants and helpers from our new modules
from config import TABLE_L5_RAW_MESSAGES, TABLE_L4_STRUCTURED_RECORDS
from crypto_utils import encrypt_message, decrypt_message

# --- Decorator for Error Handling ---
def handle_db_errors(default_return_value=None):
    """A decorator to handle Supabase exceptions and show errors in Streamlit."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                st.error(f"Database operation failed in {func.__name__}: {e}")
                return default_return_value
        return wrapper
    return decorator

# --- Database Functions ---

@handle_db_errors()
def save_message(supabase: Client, key: bytes, conversation_id: str, role: str, content: str, user_id: str):
    """Saves a raw L5 message to the database."""
    encrypted_content = encrypt_message(content, key)
    supabase.table(TABLE_L5_RAW_MESSAGES).insert({
        "conversation_id": conversation_id, "role": role,
        "content": encrypted_content, "user_id": user_id
    }).execute()

@handle_db_errors(default_return_value=[])
def load_messages_for_conversation(supabase: Client, key: bytes, conversation_id: str):
    """Loads and decrypts all L5 messages for a given conversation."""
    response = supabase.table(TABLE_L5_RAW_MESSAGES).select("role, content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
    decrypted_messages = []
    for msg in response.data:
        try:
            decrypted_content = decrypt_message(msg['content'], key)
            decrypted_messages.append({'role': msg['role'], 'content': decrypted_content})
        except Exception:
            decrypted_messages.append({'role': msg['role'], 'content': '[Cannot Decrypt Message]'})
    return decrypted_messages

@handle_db_errors()
def create_interim_summary(supabase: Client, key: bytes, conversation_id: str, user_id: str, first_message_content: str):
    """Creates an encrypted, interim L4 record."""
    summary_obj = {
        "why_summary": "[下書き] " + first_message_content[:50].strip() + "...",
        "what_summary": first_message_content[:100].strip(),
        "how_summary": ""
    }
    encrypted_summary = encrypt_message(json.dumps(summary_obj, ensure_ascii=False), key)
    supabase.table(TABLE_L4_STRUCTURED_RECORDS).insert({
        "user_id": user_id,
        "conversation_id": conversation_id,
        "summary_data": encrypted_summary,
        "status": "interim"
    }).execute()
    st.toast(f"Draft saved.")

@handle_db_errors(default_return_value=(None, None))
def get_latest_l4_record(supabase: Client, key: bytes, conversation_id: str):
    """Fetches and decrypts the most recent L4 record for a conversation."""
    response = supabase.table(TABLE_L4_STRUCTURED_RECORDS).select("id, summary_data").eq("conversation_id", conversation_id).order("created_at", desc=True).limit(1).execute()
    if response.data:
        record_id = response.data[0]['id']
        decrypted_summary = decrypt_message(response.data[0]['summary_data'], key)
        return record_id, decrypted_summary
    return None, None

@handle_db_errors()
def insert_finalized_summary(supabase: Client, key: bytes, conversation_id: str, user_id: str, summary_obj: dict, supersedes_id: str):
    """Inserts a new 'finalized' L4 record into the database."""
    encrypted_summary = encrypt_message(json.dumps(summary_obj, ensure_ascii=False), key)
    supabase.table(TABLE_L4_STRUCTURED_RECORDS).insert({
        "user_id": user_id,
        "conversation_id": conversation_id,
        "summary_data": encrypted_summary,
        "status": "finalized",
        "supersedes_id": supersedes_id
    }).execute()
    st.toast(f"Knowledge crystallized!")

@handle_db_errors(default_return_value=[])
def load_conversation_history(supabase: Client, key: bytes, user_id: str):
    """Loads and decrypts the latest L4 record title for each conversation."""
    response = supabase.table(TABLE_L4_STRUCTURED_RECORDS).select("conversation_id, summary_data, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
    if not response.data: return []
    
    df = pd.DataFrame(response.data)
    latest_records_df = df.drop_duplicates(subset=['conversation_id'])
    latest_records_df = latest_records_df.sort_values(by="created_at", ascending=True)
    
    history_list = []
    for index, row in latest_records_df.iterrows():
        try:
            decrypted_summary = decrypt_message(row['summary_data'], key)
            summary_obj = json.loads(decrypted_summary)
            preview_title = summary_obj.get('why_summary', '[Cannot read summary]')
            history_list.append({'conversation_id': row['conversation_id'], 'preview': preview_title})
        except Exception:
            history_list.append({'conversation_id': row['conversation_id'], 'preview': '[Cannot Decrypt Summary]'})
    return history_list

@handle_db_errors()
def save_language_preference(supabase: Client, lang_code: str):
    """Saves the user's language preference."""
    supabase.auth.update_user({"data": {"language_preference": lang_code}})