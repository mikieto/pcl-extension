import streamlit as st

@st.cache_data
def load_prompt(language):
    """Loads the system prompt from a file."""
    try:
        filename = f"prompts/system_prompt_{language}.txt"
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Prompt file for {language} not found.")
        return "You are a helpful assistant."

@st.cache_data
def load_summarize_prompt(language):
    """Loads the summarization prompt from a file."""
    try:
        filename = f"prompts/summarize_why_prompt_{language}.txt"
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Summarize the following conversation: {conversation_text}"