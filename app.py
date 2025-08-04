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

# --- Configuration & Connections ---
SYSTEM_PROMPT = """
# Role & Goal
You are a world-class strategic partner for organizing the user's thoughts and producing better outcomes.
Your ultimate goal is not just to answer questions, but to help the user reach the "core of their idea (Why)," create a concrete action plan (How), and maximize the quality of the final deliverable (What).
# Core Process
Always follow these 4 steps in your interaction:
1. **Acknowledge the initial idea (What)**:
   First, positively receive the user's initial request or idea and show that you understand it.
2. **Gently probe for the purpose (Why)**:
   Instead of directly asking "Why do you need that?", approach the core with a collaborative attitude. The goal is to make it clear that you are asking in order to provide the best support.
   **Effective questions**:
   - "That sounds interesting! To provide the best possible support, could you tell me a bit about the background? What is the ultimate goal you want to achieve?"
   - "Got it. What does 'success' look like for this task?"
   - "Who is the intended audience for that document, and in what context will they be reading it?"
3. **Co-create the method (How)**:
   Once the objective (Why) is clear, brainstorm multiple concrete methods for implementation (How), present the pros and cons of each, and support the user in making the best choice.
4. **Refine the deliverable (What)**:
   Based on the selected method, help sublimate the initial idea into a more refined, concrete deliverable.
# General Rules
- Always maintain an encouraging and supportive attitude.
- If you feel the user's thinking is stagnating, intentionally present a different perspective (like a devil's advocate: "From an opposing viewpoint...").
- Be mindful of always ending your response with a question that advances the user's thinking to the next step.
"""

try:
    url: str = st.secrets.supabase.url
    key: str = st.secrets.supabase.key
    supabase: Client = create_client(url, key)
    genai.configure(api_key=st.secrets.gemini.api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Could not connect to services: {e}")
    st.stop()

# --- Encryption Helper Functions (Same as before) ---
def derive_key(password: str, salt: bytes) -> bytes:
    # ...
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_message(message: str, key: bytes) -> str:
    # ...
    f = Fernet(key)
    return f.encrypt(message.encode()).decode()

def decrypt_message(encrypted_message: str, key: bytes) -> str:
    # ...
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

# --- Authentication Logic (Same as before) ---
if not st.session_state.user_session or not st.session_state.encryption_key:
    # ... (Login/Sign Up form is the same)
    st.header("Login / Sign Up")
    form_choice = st.radio("Choose action:", ["Login", "Sign Up"])
    
    with st.form("auth_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button(label=form_choice)

        if submit_button:
            if form_choice == "Sign Up":
                try:
                    supabase.auth.sign_up({"email": email, "password": password})
                    st.success("Sign up successful! Please check your email to verify.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")
            elif form_choice == "Login":
                try:
                    user_session = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user_session = user_session
                    st.session_state.encryption_key = derive_key(password, user_session.user.id.encode())
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
else:
    # --- Main Application Logic (runs only if logged in) ---
    session = st.session_state.user_session
    encryption_key = st.session_state.encryption_key
    user_id = session.user.id
    user_email = session.user.email

    # --- Helper Functions (Same as before) ---
    def save_message(conversation_id, role, content, user_id, key):
        # ...
        encrypted_content = encrypt_message(content, key)
        try:
            supabase.table("l4_records_messages").insert({
                "conversation_id": conversation_id, "role": role,
                "content": encrypted_content, "user_id": user_id
            }).execute()
        except Exception as e:
            st.error(f"Failed to save message: {e}")

    def load_conversations(user_id, key):
        # ...
        try:
            response = supabase.table("l4_records_messages").select("conversation_id, content, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
            if not response.data:
                return []
            df = pd.DataFrame(response.data)
            unique_convs = df.drop_duplicates(subset=['conversation_id']).copy()
            previews = []
            for index, row in unique_convs.iterrows():
                try:
                    decrypted_content = decrypt_message(row['content'], key)
                    preview_text = decrypted_content[:40] + '...'
                except Exception:
                    preview_text = '[Encrypted Data]'
                previews.append({
                    'conversation_id': row['conversation_id'],
                    'preview': preview_text
                })
            return previews
        except Exception as e:
            st.error(f"Failed to load conversations: {e}")
            return []

    def load_messages_for_conversation(conversation_id, key):
        # ...
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

    # --- Sidebar (Simplified: No file uploader here anymore) ---
    with st.sidebar:
        st.write(f"Welcome {user_email}")
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
    
    # ▼▼▼ NEW: Unified Multimodal Input ▼▼▼
    if prompt_data := st.chat_input("Ask a question or upload a file...", accept_file=True):
        # The prompt_data is a dictionary with "text" and "files" keys
        
        user_text = prompt_data["text"]
        uploaded_files = prompt_data["files"]

        final_prompt = user_text
        display_prompt = user_text
        
        if uploaded_files:
            # For now, we'll handle the first file
            uploaded_file = uploaded_files[0]
            try:
                file_content = uploaded_file.getvalue().decode("utf-8")
                final_prompt = f"Instruction: {user_text}\n\nDocument:\n---\n{file_content}"
                display_prompt = f"**Instruction for `{uploaded_file.name}`:**\n{user_text}"
            except Exception as e:
                st.error(f"Error reading file: {e}")
                final_prompt = None

        if final_prompt:
            st.session_state.messages.append({"role": "user", "content": final_prompt})
            with st.chat_message("user"):
                st.markdown(display_prompt)
            save_message(st.session_state.conversation_id, "user", final_prompt, user_id, encryption_key)

            # --- Gemini API Call ---
            with st.spinner("Thinking..."):
                try:
                    api_request_messages = [{"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]} for msg in st.session_state.messages]
                    full_history = [{"role": "user", "parts": [SYSTEM_PROMPT]}, {"role": "model", "parts": ["Understood. I am ready to act as your strategic partner. How can I help you today?"]},] + api_request_messages
                    
                    response = model.generate_content(full_history)
                    response_text = response.text

                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    with st.chat_message("assistant"):
                        st.markdown(response_text)
                    save_message(st.session_state.conversation_id, "assistant", response_text, user_id, encryption_key)

                except Exception as e:
                    st.error(f"An error occurred with the Gemini API: {e}")
