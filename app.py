# app.py

import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import uuid
import pandas as pd
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- Helper function to load prompts ---
@st.cache_data
def load_prompt(language):
    """Loads the system prompt from a file."""
    try:
        filename = f"prompts/system_prompt_{language}.txt"
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Prompt file for {language} not found.")
        return "You are a helpful assistant." # Fallback prompt

# --- Connections ---
try:
    url: str = st.secrets.supabase.url
    key: str = st.secrets.supabase.key
    supabase: Client = create_client(url, key)
    genai.configure(api_key=st.secrets.gemini.api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Could not connect to services: {e}")
    st.stop()

# --- Encryption Helper Functions ---
def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_message(message: str, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(message.encode()).decode()

def decrypt_message(encrypted_message: str, key: bytes) -> str:
    f = Fernet(key)
    return f.decrypt(encrypted_message.encode()).decode()

# --- App ---
st.title("PCL Navigator 🧠")

# --- Session State Initialization ---
if 'user_session' not in st.session_state:
    st.session_state.user_session = None
if 'encryption_key' not in st.session_state:
    st.session_state.encryption_key = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
if "language" not in st.session_state:
    st.session_state.language = "en"

# --- Authentication Logic ---
if not st.session_state.user_session or not st.session_state.encryption_key:
    st.header("Login / Sign Up")
    form_choice = st.radio("Choose action:", ["Login", "Sign Up"])
    
    with st.form("auth_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button(label=form_choice)

        if submit_button:
            if form_choice == "Sign Up":
                try:
                    user_metadata = {"language_preference": "en"}
                    supabase.auth.sign_up({"email": email, "password": password, "options": {"data": user_metadata}})
                    st.success("Sign up successful! Please check your email to verify.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")
            elif form_choice == "Login":
                try:
                    user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user_session = user_session
                    st.session_state.encryption_key = derive_key(password, user_session.user.id.encode())
                    lang_pref = user_session.user.user_metadata.get("language_preference", "en")
                    st.session_state.language = lang_pref
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
else:
    # --- Main Application Logic ---
    session = st.session_state.user_session
    encryption_key = st.session_state.encryption_key
    user_id = session.user.id
    user_email = session.user.email
    
    supabase.auth.set_session(session.session.access_token, session.session.refresh_token)

    # --- Helper Functions ---
    def save_message(conversation_id, role, content, user_id, key):
        encrypted_content = encrypt_message(content, key)
        try:
            supabase.table("l4_records_messages").insert({
                "conversation_id": conversation_id, "role": role,
                "content": encrypted_content, "user_id": user_id
            }).execute()
        except Exception as e:
            st.error(f"Failed to save message: {e}")

    def load_conversations(user_id, key):
        try:
            response = supabase.table("l4_records_messages").select("conversation_id, content, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
            if not response.data: return []
            df = pd.DataFrame(response.data)
            unique_convs = df.drop_duplicates(subset=['conversation_id']).copy()
            previews = []
            for index, row in unique_convs.iterrows():
                try:
                    decrypted_content = decrypt_message(row['content'], key)
                    preview_text = decrypted_content[:40] + '...'
                except Exception:
                    preview_text = '[Encrypted Data]'
                previews.append({'conversation_id': row['conversation_id'], 'preview': preview_text})
            return previews
        except Exception as e:
            st.error(f"Failed to load conversations: {e}")
            return []

    def load_messages_for_conversation(conversation_id, key):
        try:
            response = supabase.table("l4_records_messages").select("role, content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
            decrypted_messages = []
            for msg in response.data:
                try:
                    decrypted_content = decrypt_message(msg['content'], key)
                    decrypted_messages.append({'role': msg['role'], 'content': decrypted_content})
                except Exception:
                    decrypted_messages.append({'role': msg['role'], 'content': '[Cannot Decrypt Message]'})
            return decrypted_messages
        except Exception as e:
            st.error(f"Failed to load/decrypt messages: {e}")
            return []
    
    def save_language_preference(lang_code):
        try:
            supabase.auth.update_user({"data": {"language_preference": lang_code}})
        except Exception as e:
            st.error(f"Failed to save language preference: {e}")

    # --- Sidebar ---
    with st.sidebar:
        st.write(f"Welcome {user_email}")
        lang_map = {"English": "en", "日本語": "ja"}
        lang_name_list = list(lang_map.keys())
        current_lang_index = lang_name_list.index("日本語") if st.session_state.language == "ja" else 0
        def on_lang_change():
            selected_lang_code = lang_map[st.session_state.lang_selector]
            st.session_state.language = selected_lang_code
            save_language_preference(selected_lang_code)
        st.selectbox("Language", options=lang_name_list, index=current_lang_index, key="lang_selector", on_change=on_lang_change)
        if st.button("Logout"):
            st.session_state.user_session = None
            st.session_state.encryption_key = None
            st.session_state.messages = []
            st.rerun()
        st.markdown("---")
        if st.button("New Chat ✨"):
            st.session_state.messages = []
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()
        st.markdown("## Conversation History")
        conversations = load_conversations(user_id, encryption_key)
        if conversations:
            for conv in conversations:
                if st.button(conv['preview'], key=conv['conversation_id']):
                    st.session_state.messages = load_messages_for_conversation(conv['conversation_id'], encryption_key)
                    st.session_state.conversation_id = conv['conversation_id']
                    st.rerun()

    # --- Main Chat Interface ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # ▼▼▼ THIS IS THE CORRECTED SECTION ▼▼▼
    if prompt_data := st.chat_input("Start a new chat or upload a file...", accept_file=True):
        
        user_text = prompt_data["text"]
        uploaded_files = prompt_data["files"]
        
        # This is the full content that gets saved and sent to the AI
        final_prompt_for_ai = user_text
        # This is what gets displayed in the chat history for the user
        display_prompt = user_text

        if uploaded_files:
            try:
                uploaded_file = uploaded_files[0]
                file_content = uploaded_file.getvalue().decode("utf-8")
                final_prompt_for_ai = f"Instruction: {user_text}\n\nDocument:\n---\n{file_content}"
                display_prompt = f"**Instruction for `{uploaded_file.name}`:**\n{user_text}"
            except Exception as e:
                st.error(f"Error reading file: {e}")
                final_prompt_for_ai = None

        if final_prompt_for_ai:
            st.session_state.messages.append({"role": "user", "content": display_prompt})
            save_message(st.session_state.conversation_id, "user", final_prompt_for_ai, user_id, encryption_key)

            with st.spinner("Thinking..."):
                try:
                    # Prepare history for AI, ensuring the last message has the full file content
                    ai_request_messages = st.session_state.messages[:-1] + [{"role": "user", "content": final_prompt_for_ai}]
                    
                    api_request_parts = [{"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]} for msg in ai_request_messages]
                    SYSTEM_PROMPT = load_prompt(st.session_state.language)
                    full_history = [{"role": "user", "parts": [SYSTEM_PROMPT]}, {"role": "model", "parts": ["Understood."]},] + api_request_parts
                    
                    response = model.generate_content(full_history)
                    response_text = response.text
                    
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    save_message(st.session_state.conversation_id, "assistant", response_text, user_id, encryption_key)
                except Exception as e:
                    st.error(f"An error occurred with the Gemini API: {e}")
            
            st.rerun()