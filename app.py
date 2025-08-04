# app.py

import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import uuid
from streamlit_supabase_auth import login_form, logout_button
import pandas as pd

# --- Configuration ---
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

# --- Connections ---
try:
    url: str = st.secrets.supabase.url
    key: str = st.secrets.supabase.key
    supabase: Client = create_client(url, key)
    genai.configure(api_key=st.secrets.gemini.api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Could not connect to services. Please check your secrets.toml file. Error: {e}")
    st.stop()

# --- App UI & Authentication ---
st.title("PCL Navigator MVP 🧠")

session = login_form(
    url=st.secrets.supabase.url,
    apiKey=st.secrets.supabase.key
)

# --- Main App Logic (runs only if logged in) ---
if session:
    user_id = session['user']['id']
    user_email = session['user']['email']

    # --- Helper Functions ---
    def save_message(conversation_id, role, content, user_id):
        try:
            supabase.table("l4_records_messages").insert({
                "conversation_id": conversation_id, "role": role,
                "content": content, "user_id": user_id
            }).execute()
        except Exception as e:
            st.error(f"Failed to save message: {e}")

    def load_conversations(user_id):
        """Fetches the most recent message from each conversation to use as a preview."""
        try:
            response = supabase.table("l4_records_messages").select("conversation_id, content, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
            if not response.data:
                return []
            
            df = pd.DataFrame(response.data)
            df['content'] = df['content'].fillna('')
            # Since the data is sorted by date descending, dropping duplicates
            # will keep the most recent message for each conversation.
            unique_conversations = df.drop_duplicates(subset=['conversation_id'])
            return unique_conversations.to_dict('records')
        except Exception as e:
            st.error(f"Failed to load conversations: {e}")
            return []

    def load_messages_for_conversation(conversation_id):
        """Fetches all messages for a selected conversation."""
        try:
            response = supabase.table("l4_records_messages").select("role, content").eq("conversation_id", conversation_id).order("created_at", desc=False).execute()
            return response.data
        except Exception as e:
            st.error(f"Failed to load messages: {e}")
            return []

    # --- Sidebar UI ---
    with st.sidebar:
        st.write(f"Welcome {user_email}")
        
        if st.button("New Chat ✨"):
            st.session_state.messages = []
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()

        st.markdown("---")
        st.markdown("## Conversation History")
        
        conversations = load_conversations(user_id)
        if conversations:
            for conv in conversations:
                preview = conv['content'][:40] + '...' if conv['content'] else "Empty Chat"
                if st.button(preview, key=conv['conversation_id']):
                    st.session_state.messages = load_messages_for_conversation(conv['conversation_id'])
                    st.session_state.conversation_id = conv['conversation_id']
                    st.rerun()
        else:
            st.write("No conversations yet.")
        
        # This now only runs AFTER the login form is gone, preventing duplicate keys.
        logout_button(url=st.secrets.supabase.url, apiKey=st.secrets.supabase.key)

    # --- Session State Initialization ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = str(uuid.uuid4())

    # --- Main Chat Interface ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("What would you like to work on?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        save_message(st.session_state.conversation_id, "user", prompt, user_id)

        with st.spinner("Thinking..."):
            try:
                api_request_messages = [
                    {"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]}
                    for msg in st.session_state.messages
                ]
                full_history = [
                    {"role": "user", "parts": [SYSTEM_PROMPT]},
                    {"role": "model", "parts": ["Understood. I am ready to act as your strategic partner. How can I help you today?"]},
                ] + api_request_messages
                
                response = model.generate_content(full_history)
                response_text = response.text

                with st.chat_message("assistant"):
                    st.markdown(response_text)
                
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                save_message(st.session_state.conversation_id, "assistant", response_text, user_id)
            except Exception as e:
                st.error(f"An error occurred with the Gemini API: {e}")