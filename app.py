import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import uuid

# Import from our new modules
from config import TABLE_L4_STRUCTURED_RECORDS, TABLE_L5_RAW_MESSAGES
from crypto_utils import derive_key
from supabase_client import (
    save_message,
    create_interim_summary,
    load_messages_for_conversation,
    load_conversation_history,
    save_language_preference
)
from crystallizer import finalize_summary
from utils import load_prompt, load_summarize_prompt

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
    # ... (Authentication code remains the same) ...
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

    # --- Sidebar ---
    with st.sidebar:
        st.write(f"Welcome {user_email}")
        lang_map = {"English": "en", "日本語": "ja"}
        lang_name_list = list(lang_map.keys())
        current_lang_index = lang_name_list.index("日本語") if st.session_state.language == "ja" else 0
        
        def on_lang_change():
            selected_lang_code = lang_map[st.session_state.lang_selector]
            st.session_state.language = selected_lang_code
            save_language_preference(supabase, selected_lang_code)

        st.selectbox("Language", options=lang_name_list, index=current_lang_index, key="lang_selector", on_change=on_lang_change)
        
        if st.button("Logout"):
            st.session_state.user_session = None
            st.session_state.encryption_key = None
            st.session_state.messages = []
            st.rerun()

        st.markdown("---")

        if st.button("New Chat ✨"):
            previous_conversation_id = st.session_state.conversation_id
            if st.session_state.messages:
                with st.spinner("Finalizing last conversation..."):
                    finalize_summary(model, supabase, encryption_key, previous_conversation_id, user_id, st.session_state.language)
            
            st.session_state.messages = []
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()

        st.markdown("## Conversation History")
        conversations = load_conversation_history(supabase, encryption_key, user_id)
        if conversations:
            for conv in conversations:
                if st.button(conv['preview'], key=conv['conversation_id']):
                    previous_conversation_id = st.session_state.conversation_id
                    if st.session_state.messages and previous_conversation_id != conv['conversation_id']:
                         with st.spinner("Finalizing last conversation..."):
                            finalize_summary(model, supabase, encryption_key, previous_conversation_id, user_id, st.session_state.language)
                    
                    st.session_state.messages = load_messages_for_conversation(supabase, encryption_key, conv['conversation_id'])
                    st.session_state.conversation_id = conv['conversation_id']
                    st.rerun()

    # --- Main Chat Interface ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt_data := st.chat_input("Start a new chat or upload a file...", accept_file=True):
        user_text = prompt_data["text"]
        uploaded_files = prompt_data["files"]
        final_prompt_for_ai = user_text
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
            is_first_message = not st.session_state.messages
            st.session_state.messages.append({"role": "user", "content": display_prompt})
            save_message(supabase, encryption_key, st.session_state.conversation_id, "user", final_prompt_for_ai, user_id)
            
            if is_first_message:
                create_interim_summary(supabase, encryption_key, st.session_state.conversation_id, user_id, final_prompt_for_ai)
            
            with st.spinner("Thinking..."):
                try:
                    ai_request_messages = st.session_state.messages[:-1] + [{"role": "user", "content": final_prompt_for_ai}]
                    api_request_parts = [{"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]} for msg in ai_request_messages]
                    SYSTEM_PROMPT = load_prompt(st.session_state.language)
                    full_history = [{"role": "user", "parts": [SYSTEM_PROMPT]}, {"role": "model", "parts": ["Understood."]},] + api_request_parts
                    
                    response = model.generate_content(full_history)
                    response_text = response.text
                    
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    save_message(supabase, encryption_key, st.session_state.conversation_id, "assistant", response_text, user_id)
                except Exception as e:
                    st.error(f"An error occurred with the Gemini API: {e}")
            st.rerun()