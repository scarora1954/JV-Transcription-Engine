from dotenv import load_dotenv
load_dotenv()  # Scans for a local .env file and imports secret credentials automatically

import os
import re
import time
import io
import streamlit as st
import google.genai as genai
from google.genai import types
from pydub import AudioSegment
from datetime import datetime 
# transcriberV1.py में सबसे ऊपर (Imports के साथ) जोड़ें:
from audio_utils import slice_audio_to_bytes

# ==========================================
# 1. CONFIGURATION & STATE INITIALIZATION
# ==========================================
st.set_page_config(page_title="Gemini Verbatim Transcription Engine", layout="wide")

# Check if a private key is set in the environment variables (or loaded via dotenv)
PRIVATE_KEY = os.environ.get("GEMINI_API_KEY", "")
IS_PRIVATE_MODE = len(PRIVATE_KEY) > 0

# Initialize persistent session states
if "api_key" not in st.session_state:
    st.session_state.api_key = PRIVATE_KEY if IS_PRIVATE_MODE else ""
if "formatted_output" not in st.session_state:
    st.session_state.formatted_output = ""
if "download_filename" not in st.session_state:
    st.session_state.download_filename = "word_to_word_transcript.md"
if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = 0.0

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

def chunk_by_sentences(text, sentence_limit):
    """Splits raw text dynamically at sentence boundaries to maintain context."""
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

# def slice_audio_to_bytes(uploaded_file, chunk_minutes):
#     """Slices a large audio file completely in-memory into raw byte-segment blocks."""
#     audio = AudioSegment.from_file(io.BytesIO(uploaded_file.read()))
#     chunk_length_ms = chunk_minutes * 60 * 1000 
    
#     byte_chunks = []
#     _, ext = os.path.splitext(uploaded_file.name)
#     format_str = ext.replace(".", "").lower()
    
#     if format_str == "m4a":
#         format_str = "ipod"
        
#     for i in range(0, len(audio), chunk_length_ms):
#         chunk = audio[i:i + chunk_length_ms]
#         chunk_buffer = io.BytesIO()
#         chunk.export(chunk_buffer, format=format_str)
#         byte_chunks.append(chunk_buffer.getvalue())
        
#     return byte_chunks, ext.lower()

def save_local_backup(filename, content):
    """Saves a local backup of the processed transcript immediately to prevent data loss."""
    try:
        backup_dir = "transcripts_backup"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        backup_path = os.path.join(backup_dir, filename)
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
        st.sidebar.success(f"💾 स्थानीय बैकअप सुरक्षित: {backup_path}")
    except Exception as backup_error:
        st.sidebar.error(f"स्थानीय बैकअप सहेजने में त्रुटि: {backup_error}")

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
    st.subheader("🤖 Model Selection")
    
    model_options = {
        "Gemini Flash-Lite Latest Default":"gemini-flash-lite-latest"
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 3.0 Flash": "gemini-3.0-flash",
        "Gemini 3.5 Flash ": "gemini-3.5-flash",
        "Gemini Latest Flash": "gemini-flash-latest"
    }
    
    selected_model_display = st.selectbox(
        "Select Gemini Model Version",
        options=list(model_options.keys()),
        index=0,
        help="Select the specific Gemini model engine version for the pipeline."
    )
    selected_model_id = model_options[selected_model_display]

    selected_temp = st.slider(
        label="모델 तापमान (Temperature) चुनें",
        min_value=0.0,
        max_value=1.0,
        value=0.0,      
        step=0.1,
        help="0.0 = पूर्णतः अक्षरशः (Verbatim) और सटीक। 1.0 = अधिक रचनात्मक और भाषाई विविधता।"
    )
    st.write("---")
    st.subheader("🎛️ Dynamic Boundaries")
    
    audio_chunk_limit = st.slider(
        "Audio Split Interval (Minutes)",
        min_value=1,
        max_value=10,
        value=10,
        step=1,
        help="Slices large input media automatically into these lengths before sending inline bytes to the API."
    )
    
    sentence_limit = st.slider(
        "Max Sentences per Text Chunk", 
        min_value=5, 
        max_value=100, 
        value=30, 
        step=5,
        help="Controls how many sentences are bundled together when sending messy text to Gemini."
    )
    
    st.write("---")
    st.subheader("Prompt Directory Branch Status")
    for k, filepath in PROMPT_FILES.items():
        status = "✅ Found" if os.path.exists(filepath) else "❌ Missing"
        st.caption(f"**{filepath}**: {status}")
        
    st.write("---")
    if st.button("🔄 Start New Job", use_container_width=True):
        st.session_state.formatted_output = ""
        st.session_state.download_filename = "word_to_word_transcript.md"
        st.session_state.elapsed_time = 0.0
        st.toast("Pipeline cleared! Ready for next job.", icon="✅")

# ==========================================
# 4. MAIN USER INTERFACE & TABS
# ==========================================
st.title("🎙️ Gemini Word-to-Word Transcription & Formatting Engine")
st.caption("Verbatim transcription pipeline handling dynamic in-memory base64 binary streaming.")

tab1, tab2 = st.tabs(["🎵 Audio Input", "📄 Raw Text Input"])

# ------------------------------------------
# TAB 1: AUDIO INPUT
# ------------------------------------------
with tab1:
    st.header("Audio Verbatim Transcription")
    input_lang_audio = st.selectbox("Select Audio Language", ["English", "Hindi"], key="audio_lang")
    audio_file = st.file_uploader("Upload Audio File (In-memory chunking)", type=["wav", "mp3", "m4a"])
    
    if audio_file and st.button("Process Audio Pipeline"):
        client = get_gemini_client()
        
        if client:
            start_time = time.time()
            try:
                base_name, _ = os.path.splitext(audio_file.name)
                current_time = datetime.now().strftime("%Y%m%d_%H%M")
                
                # सुव्यवस्थित फ़ाइल नाम प्रबन्धन (.md एक्सटेंशन के साथ)
                st.session_state.download_filename = f"{base_name}_{current_time}.md"
                
                with st.spinner(f"FFmpeg partitioning audio into {audio_chunk_limit}-minute memory chunks..."):
                    audio_chunks, raw_extension = slice_audio_to_bytes(audio_file, audio_chunk_limit)
                
                mime_type = "audio/wav"
                if raw_extension == ".mp3":
                    mime_type = "audio/mp3"
                elif raw_extension in [".m4a", ".mp4"]:
                    mime_type = "audio/mp4"

                compiled_transcripts = []
                total_chunks = len(audio_chunks)
                
                audio_progress = st.progress(0)
                for idx, chunk_bytes in enumerate(audio_chunks):
                    with st.spinner(f"Processing in-memory base64 payload segment {idx + 1} of {total_chunks} via {selected_model_display}..."):
                        
                        prompt_key = f"audio_{input_lang_audio}"
                        fallback = f"Provide a clean, word-for-word verbatim transcript of this audio in {input_lang_audio}. Keep the exact word structure spoken without additions."
                        configured_prompt = load_external_prompt(prompt_key, fallback)
                        
                        inline_audio_part = types.Part.from_bytes(
                            data=chunk_bytes,
                            mime_type=mime_type
                        )
                        
                        response = client.models.generate_content(
                            model=selected_model_id,
                            contents=[inline_audio_part, configured_prompt],
                            config=types.GenerateContentConfig(
                                temperature=selected_temp,
                                top_p=0.1
                            )
                        )
                        compiled_transcripts.append(response.text)
                    
                    audio_progress.progress((idx + 1) / total_chunks)
                    
                st.session_state.formatted_output = "\n\n".join(compiled_transcripts)
                st.session_state.elapsed_time = time.time() - start_time
                
                # यहाँ से पुरानी भ्रम पैदा करने वाली st.code लाइनों को हटा दिया गया है
                
                save_local_backup(st.session_state.download_filename, st.session_state.formatted_output)
                
            except Exception as e:
                st.error(f"API/System Execution Error: {e}")

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
            with st.spinner(f"Processing sentence boundary chunks (Limit: {sentence_limit})..."):
                start_time = time.time()
                try:
                    current_time = datetime.now().strftime("%Y%m%d_%H%M")
                    
                    # टाइमस्टैम्प आधारित सुसंगत फ़ाइल नामकरण प्रणाली (.md प्रारूप में)
                    st.session_state.download_filename = f"formatted_text_{input_lang_text.lower()}_{current_time}.md"
                    
                    chunks = chunk_by_sentences(raw_text, sentence_limit)
                    compiled_results = []
                    
                    prompt_key = f"text_{input_lang_text}"
                    fallback = f"Clean, structure, and provide a word-for-word formatted version of this {input_lang_text} text. Preserve all spoken words exactly."
                    configured_prompt = load_external_prompt(prompt_key, fallback)
                    
                    progress_bar = st.progress(0)
                    for idx, chunk in enumerate(chunks):
                        full_prompt = f"{configured_prompt}\n\n[Text Segment to Process]\n{chunk}"
                        response = client.models.generate_content(
                            model=selected_model_id,
                            contents=full_prompt,
                        )
                        compiled_results.append(response.text)
                        progress_bar.progress((idx + 1) / len(chunks))
                        
                    st.session_state.formatted_output = "\n\n".join(compiled_results)
                    st.session_state.elapsed_time = time.time() - start_time
                    
                    save_local_backup(st.session_state.download_filename, st.session_state.formatted_output)
                    
                except Exception as e:
                    st.error(f"Processing Error: {e}")

# ==========================================
# 5. GLOBAL OUTPUT PIPELINE (METRICS, DISPLAY & DOWNLOAD)
# ==========================================
if st.session_state.formatted_output:
    st.write("---")
    st.subheader("📋 Verbatim Word-to-Word Output")
    word_count = len(st.session_state.formatted_output.split())
    
    col_metric1, col_metric2 = st.columns(2)
    with col_metric1:
        st.metric("Total Word Count", f"{word_count:,} words")
    with col_metric2:
        st.metric("Gemini API Processing Time", f"{st.session_state.elapsed_time:.2f} seconds")
        
    st.markdown(st.session_state.formatted_output, unsafe_allow_html=True)
    
    st.write("")
    
    # दोनों टैब्स के लिए पूरी तरह एकीकृत, स्वच्छ डाउनलोड बटन प्रबन्धन
    st.download_button(
        label=f"📥 संशोधित पाठ डाउनलोड करें ({st.session_state.download_filename})",
        data=st.session_state.formatted_output,
        file_name=st.session_state.download_filename,
        mime="text/plain",
        use_container_width=True
    )
