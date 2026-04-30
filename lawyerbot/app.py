import streamlit as st
from groq import Groq
from rag_engine import PakistanLawEngine
import os
import requests

# --- INITIAL SETUP ---
st.set_page_config(page_title="Pak Law AI", layout="wide")

# Note: Keeping your key here as requested, but recommend using st.secrets for safety later
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
client = Groq(api_key=GROQ_API_KEY)

# Removed unused RAG engine initialization. It's now handled entirely by the backend (server.py).

# --- HELPER FUNCTION TO PREVENT RATE LIMITS ---
def limit_tokens(text, max_words=800):
    """Simple word-based truncation to stay under Groq TPM limits."""
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "... (truncated for brevity)"
    return text

# --- UI INTERFACE ---
st.title("⚖️ Pakistan Legal Guidance Assistant")
st.info("General legal guidance based on uploaded Law Books. Not a substitute for a lawyer.")

# --- SIDEBAR BOOKING ---
with st.sidebar:
    st.header("⚖️ Book a Consultation")
    st.write("Need professional legal help? Schedule a meeting with our legal team.")
    
    with st.form("booking_form"):
        name = st.text_input("Full Name")
        phone = st.text_input("Phone Number")
        email = st.text_input("Email Address")
        notes = st.text_area("Briefly describe your case")
        
        submit_btn = st.form_submit_button("Request Consultation")
        
        if submit_btn:
            if not name or not phone or not email:
                st.error("Please fill in all required fields.")
            else:
                try:
                    payload = {
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "notes": notes
                    }
                    # Pointing to the backend server (default 8513)
                    resp = requests.post("http://127.0.0.1:8513/appointments", json=payload)
                    if resp.status_code == 200:
                        st.success("✅ Consultation requested! You and our legal team will receive confirmation emails.")
                    else:
                        st.error(f"Error: {resp.text}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display Chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Logic
if prompt := st.chat_input("Ask about Pakistani Law (e.g., What is Section 144?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing legal texts..."):
            try:
                payload = {
                    "query": prompt,
                    "history": [
                        {"role": m["role"], "content": m["content"]} 
                        for m in st.session_state.messages[:-1]
                    ]
                }
                res = requests.post("http://127.0.0.1:8513/chat", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    response = data.get("response", "Error getting response.")
                    st.markdown(response)
                    
                    if data.get("sources"):
                        with st.expander("View Cited Sources"):
                            for s in data["sources"]:
                                st.write(f"**{s['source']}**: {s['preview']}...")
                else:
                    response = f"Backend Error: {res.text}"
                    st.error(response)
            except Exception as e:
                response = f"Failed to connect to backend: {e}"
                st.error(response)

    st.session_state.messages.append({"role": "assistant", "content": response})