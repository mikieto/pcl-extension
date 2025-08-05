import streamlit as st
import json
from supabase import Client
from google.generativeai.generative_models import GenerativeModel

# Import from our other new modules
from supabase_client import load_messages_for_conversation, get_latest_l4_record, insert_finalized_summary
from utils import load_summarize_prompt

def finalize_summary(model: GenerativeModel, supabase: Client, key: bytes, conversation_id: str, user_id: str, language: str):
    """
    Orchestrates the process of finalizing a conversation summary.
    This is the core business logic for crystallization.
    """
    messages = load_messages_for_conversation(supabase, key, conversation_id)
    if not messages: return

    # Get the previous summary to provide it as context for refinement
    previous_record_id, previous_summary_text = get_latest_l4_record(supabase, key, conversation_id)

    conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
    try:
        prompt_template = load_summarize_prompt(language)
        prompt = prompt_template.format(conversation_text=conversation_text, previous_summary=previous_summary_text or "")
        
        response = model.generate_content(prompt)
        # Basic parsing to handle potential markdown in response
        summary_text = response.text.strip().lstrip("```json").rstrip("```")
        summary_obj = json.loads(summary_text)

        # Insert the new finalized record
        insert_finalized_summary(supabase, key, conversation_id, user_id, summary_obj, previous_record_id)

    except Exception as e:
        st.error(f"Failed to finalize summary: {e}")