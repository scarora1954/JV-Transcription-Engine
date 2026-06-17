import os
import re
import streamlit as st
import google.genai as genai

# ==========================================
# 1. CONFIGURATION & STATE INITIALIZATION
# ==========================================
st.set_page_config(page_title="Gemini Verbatim Transcription Engine", layout="wide")

# Check if a private key is set in the environment variables
PRIVATE_KEY = os.environ.get("GEMINI_API_KEY", "")
IS_PRIVATE_MODE = len(PRIVATE_KEY) > 0

# Initialize persistent session states
if "api_key" not in st.session_state:
    st.session_state.api_key = PRIVATE_KEY if IS_PRIVATE_MODE else ""
if "formatted_output" not in st.session_state:
    st.session_state.formatted_output = ""

# Max sentences per chunk for raw text formatting
SENTENCE_CHUNK_LIMIT = 30  

# Mapping of file names for prompts deep in the "prompts" directory branch
PROMPT_FILES = {
    "audio_Hindi": os.path.join("prompts", "AudioH2H.txt"),
    "audio_English": os.path.join("prompts", "AudioE2E.txt"),
    "text_Hindi": os.path.join("prompts", "RawTextH2H.txt"),
    "text_English": os.path.join("prompts", "RawTextE2E.txt")
}

# ==========================================
# 2. HELPER FUNCTIONS & CHUNKING ENGINES
# ==========================================
def get_gemini_client():
    """Initializes the Gemini client using the verified API key."""
    key_to_use = PRIVATE_KEY if IS_PRIVATE_MODE else st.session_state.api_key
    if not key_to_use:
        st.error("Please enter a valid Gemini API Key to proceed.")
        return None
    return genai.Client(api_key=key_to_use)

def load_external_prompt(key, fallback_text):
    """Dynamically reads rules from external files under the prompts/ directory or returns fallback string."""
    filepath = PROMPT_FILES.get(key)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            st.sidebar.error(f"Error reading {filepath}: {e}")
    else:
        st.sidebar.warning(f"⚠️ Prompt file '{filepath}' missing. Using system fallback prompt.")
    return fallback_text

def chunk_by_sentences(text, sentence_limit=SENTENCE_CHUNK_LIMIT):
    """Splits raw text dynamically at sentence boundaries to maintain context."""
    # Splits on periods/question marks/exclamations followed by space, or Devanagari Danda (।)
    sentences = re.split(r'(?<=[.!?।])\s+', text.strip())
    chunks = []
    current_chunk = []
    
    for sentence in sentences:
        if sentence:
            current_chunk.append(sentence)
            if len(current_chunk) >= sentence_limit:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

# ==========================================
# 3. SIDEBAR (API KEY & SYSTEM CONTROL)
# ==========================================
with st.sidebar:
    st.title("System Controls")
    
    if IS_PRIVATE_MODE:
        st.success("🔒 Private Mode: API key loaded from environment.")
    else:
        st.warning("🔓 Public Mode: Key Required")
        st.session_state.api_key = st.text_input(
            "Enter Gemini API Key", 
            value=st.session_state.api_key, 
            type="password"
        )
    
    st.write("---")
    st.subheader("Prompt Directory Branch Status")
    for k, filepath in PROMPT_FILES.items():
        status = "✅ Found" if os.path.exists(filepath) else "❌ Missing"
        st.caption(f"**{filepath}**: {status}")
        
    st.write("---")
    # Reset button clears data buffers but preserves user's public API key setup
    if st.button("🔄 Start New Job", use_container_width=True):
        st.session_state.formatted_output = ""
        st.toast("Pipeline cleared! Ready for next job.", icon="✅")

# ==========================================
# 4. MAIN USER INTERFACE & TABS
# ==========================================
st.title("🎙️ Gemini Word-to-Word Transcription & Formatting Engine")
st.caption("Verbatim transcription pipeline supporting structured folder configuration files.")

# Dual Tab Interface
tab1, tab2 = st.tabs(["🎵 Audio Input", "📄 Raw Text Input"])

# ------------------------------------------
# TAB 1: AUDIO INPUT
# ------------------------------------------
with tab1:
    st.header("Audio Verbatim Transcription")
    input_lang_audio = st.selectbox("Select Audio Language", ["English", "Hindi"], key="audio_lang")
    audio_file = st.file_uploader("Upload Audio File", type=["mp3", "wav", "m4a"])
    
    if audio_file and st.button("Process Audio Pipeline"):
        client = get_gemini_client()
        if client:
            with st.spinner("Uploading and processing audio file via Gemini..."):
                try:
                    # Write temporary file to pass to Gemini API
                    temp_filename = f"temp_{audio_file.name}"
                    with open(temp_filename, "wb") as f:
                        f.write(audio_file.getbuffer())
                    
                    # Upload using the unified SDK File API
                    uploaded_file = client.files.upload(file=temp_filename)
                    
                    # Fetch instruction strategy from configured directory paths
                    prompt_key = f"audio_{input_lang_audio}"
                    fallback = f"Provide a clean, word-for-word verbatim transcript of this audio in {input_lang_audio}. Keep the exact word structure spoken without additions."
                    configured_prompt = load_external_prompt(prompt_key, fallback)
                    
                    # Call Gemini 2.5 Flash for audio multimodal processing
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[uploaded_file, configured_prompt]
                    )
                    
                    # Clean up local temp file
                    if os.path.exists(temp_filename):
                        os.remove(temp_filename)
                        
                    st.session_state.formatted_output = response.text
                    
                except Exception as e:
                    st.error(f"API Execution Error: {e}")

# ------------------------------------------
# TAB 2: RAW TEXT INPUT
# ------------------------------------------
with tab2:
    st.header("Raw Text Formatting")
    input_lang_text = st.selectbox("Select Text Language", ["English", "Hindi"], key="text_lang")
    raw_text = st.text_area("Paste Messy / Unformatted Transcript Here", height=250)
    
    if raw_text and st.button("Format Raw Text Pipeline"):
        client = get_gemini_client()
        if client:
            with st.spinner("Processing sentence boundary chunks..."):
                try:
                    chunks = chunk_by_sentences(raw_text)
                    compiled_results = []
                    
                    # Fetch instruction strategy from configured directory paths
                    prompt_key = f"text_{input_lang_text}"
                    fallback = f"Clean, structure, and provide a word-for-word formatted version of this {input_lang_text} text. Preserve all spoken words exactly."
                    configured_prompt = load_external_prompt(prompt_key, fallback)
                    
                    progress_bar = st.progress(0)
                    for idx, chunk in enumerate(chunks):
                        full_prompt = f"{configured_prompt}\n\n[Text Segment to Process]\n{chunk}"
                        
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=full_prompt,
                        )
                        compiled_results.append(response.text)
                        progress_bar.progress((idx + 1) / len(chunks))
                        
                    st.session_state.formatted_output = "\n\n".join(compiled_results)
                    
                except Exception as e:
                    st.error(f"Processing Error: {e}")

# ==========================================
# 5. GLOBAL OUTPUT PIPELINE (HTML DISPLAY & DOWNLOAD)
# ==========================================
if st.session_state.formatted_output:
    st.write("---")
    st.subheader("📋 Verbatim Word-to-Word Output")
    
    # HTML View block for raw visualization copying
    st.markdown(
        f'<div style="background-color: #f9f9f9; padding: 20px; border-radius: 8px; border-left: 5px solid #ff4b4b; color: #111111; font-family: monospace; white-space: pre-wrap;">'
        f'{st.session_state.formatted_output}'
        f'</div>', 
        unsafe_allow_html=True
    )
    
    st.write("")
    # Actions Layer
    st.download_button(
        label="📥 Download Markdown (.md)", 
        data=st.session_state.formatted_output, 
        file_name="word_to_word_transcript.md", 
        mime="text/markdown",
        use_container_width=True
    )
