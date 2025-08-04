# app.py

import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import uuid
from streamlit_supabase_auth import login_form, logout_button

SYSTEM_PROMPT = "You are a helpful partner. Always try to understand the user's core goal (the 'Why') before providing a detailed solution."

# --- Supabase Connection ---
try:
    url: str = st.secrets.supabase.url
    key: str = st.secrets.supabase.key
    supabase: Client = create_client(url, key)
except (AttributeError, KeyError):
    st.error("Supabase credentials not found.")
    st.stop()

# --- Gemini API Configuration ---
try:
    genai.configure(api_key=st.secrets.gemini.api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except (AttributeError, KeyError):
    st.error("Gemini API key not found.")
    st.stop()

# --- App UI & Authentication ---
st.title("PCL Navigator MVP 🧠")

# Run the login form. It will return a session object if login is successful.
session = login_form(
    url=st.secrets.supabase.url,
    apiKey=st.secrets.supabase.key,
    # You can add providers like "github" or "google" here
)

# If the user is not logged in, stop the app from running further.
if not session:
    st.warning("Please log in to continue.")
    st.stop()

# --- Main App Logic (runs only if logged in) ---
user_id = session['user']['id'] # Get the logged-in user's ID

# --- Helper Function to Save Messages ---
def save_message(conversation_id, role, content, user_id):
    """Saves a message to the Supabase table."""
    try:
        supabase.table("l4_records_messages").insert({
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "user_id": user_id
        }).execute()
    except Exception as e:
        st.error(f"Failed to save message to Supabase: {e}")

# --- Session State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())

# --- Display Chat History ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Chat Logic ---
if prompt := st.chat_input("What would you like to work on?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    save_message(st.session_state.conversation_id, "user", prompt, user_id)

    # Prepare and send to Gemini... (rest of the logic is the same)
    api_request_messages = [
        {"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]}
        for msg in st.session_state.messages
    ]
    # ... (SYSTEM_PROMPT logic is omitted for brevity but should be included as before)

    with st.spinner("Thinking..."):
            try:
                # Prepare the conversation history for the API call
                api_request_messages = [
                    {"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]}
                    for msg in st.session_state.messages
                ]

                # Construct the full conversation history including the system prompt
                full_history = [
                    {"role": "user", "parts": [SYSTEM_PROMPT]},
                    {"role": "model", "parts": ["Understood. I am ready to act as your strategic partner. How can I help you today?"]},
                ] + api_request_messages
                
                # Generate the response from Gemini
                response = model.generate_content(full_history)
                response_text = response.text

                # Display assistant response in UI
                with st.chat_message("assistant"):
                    st.markdown(response_text)
                
                # Add assistant response to session state
                st.session_state.messages.append({"role": "assistant", "content": response_text})

                # Save assistant message to Supabase
                save_message(st.session_state.conversation_id, "assistant", response_text, user_id)

            except Exception as e:
                st.error(f"An error occurred with the Gemini API: {e}")

# Add a logout button at the end
with st.sidebar:
    st.write(f"Welcome {session['user']['email']}")
    logout_button(
        url=st.secrets.supabase.url,
        apiKey=st.secrets.supabase.key
    )