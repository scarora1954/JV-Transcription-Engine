# audio_utils.py
import os
import subprocess
import tempfile

def slice_audio_to_bytes(audio_file, chunk_limit_mins):
    """
    बिना मेमोरी ब्लॉक किए, फिजिकल डिस्क का उपयोग करके ऑडियो को 
    तेजी से (-c copy के साथ) छोटे चंक्स में काटने वाला परिष्कृत फ़ंक्शन।
    """
    raw_extension = os.path.splitext(audio_file.name)[1].lower()
    if not raw_extension:
        raw_extension = ".m4a"
        
    audio_chunks = []
    chunk_limit_secs = chunk_limit_mins * 60

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, f"input_file{raw_extension}")
        
        with open(input_path, "wb") as f:
            f.write(audio_file.getbuffer())
            
        duration_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:noclipping=1', input_path
        ]
        try:
            total_duration = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
        except Exception:
            total_duration = 7200 

        start_time = 0
        chunk_idx = 0
        
        while start_time < total_duration:
            output_chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx}{raw_extension}")
            
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-i', input_path,
                '-t', str(chunk_limit_secs),
                '-c', 'copy',  # बिना री-एन्कोडिंग के डायरेक्ट स्लाइस
                output_chunk_path
            ]
            
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(output_chunk_path) and os.path.getsize(output_chunk_path) > 0:
                with open(output_chunk_path, "rb") as chunk_file:
                    audio_chunks.append(chunk_file.read())
            
                # पञ्चमाक्षर नियम एवं शुद्धता सुनिश्चित करने के लिए हर चंक 
                # बाइनरी रूप में सुरक्षित होकर आगे प्रोसेस होगा।
            
            start_time += chunk_limit_secs
            chunk_idx += 1

    return audio_chunks, raw_extension