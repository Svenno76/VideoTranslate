import streamlit as st
import whisper
from deep_translator import GoogleTranslator
from gtts import gTTS
import subprocess
import time
import os
import tempfile
import shutil

# Handle pydub import with error handling
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError as e:
    st.error(f"Audio processing library not available: {e}")
    st.info("Installing required system dependencies...")
    PYDUB_AVAILABLE = False
    
import zipfile
from io import BytesIO
import base64

# Configure Streamlit page
st.set_page_config(
    page_title="Video Audio Translator",
    page_icon="🎬",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .feature-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #28a745;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)

def check_dependencies():
    """Check if required system dependencies are installed"""
    missing_deps = []
    
    # Check FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        missing_deps.append("FFmpeg")
    
    # Check pydub
    if not PYDUB_AVAILABLE:
        missing_deps.append("pydub (audio processing)")
    
    if missing_deps:
        st.error("🚨 Missing Dependencies")
        st.write("The following dependencies are missing:")
        for dep in missing_deps:
            st.write(f"❌ {dep}")
        
        st.info("**Solution for Streamlit Cloud:**")
        st.code("""
# Create/update packages.txt in your repository:
ffmpeg
libavcodec-extra

# Update requirements.txt:
streamlit>=1.28.0
openai-whisper>=20230314
deep-translator>=1.11.4
gtts>=2.3.2
pydub>=0.25.1
ffmpeg-python>=0.2.0
        """)
        st.write("Then push changes to GitHub and redeploy.")
        return False
    
    return True

def extract_audio_segments(video_file, segments, temp_dir):
    """Extract audio segments from video for translation"""
    # Extract full audio from video
    audio_file = os.path.join(temp_dir, "extracted_audio.wav")
    cmd = ['ffmpeg', '-i', video_file, '-ac', '1', '-ar', '22050', '-y', audio_file]
    subprocess.run(cmd, capture_output=True, check=True)
    
    # Load the audio
    full_audio = AudioSegment.from_wav(audio_file)
    
    audio_segments = []
    for i, segment in enumerate(segments):
        start_ms = int(segment['start'] * 1000)
        end_ms = int(segment['end'] * 1000)
        
        # Extract segment
        audio_segment = full_audio[start_ms:end_ms]
        segment_file = os.path.join(temp_dir, f"segment_{i:04d}.wav")
        audio_segment.export(segment_file, format="wav")
        
        audio_segments.append({
            'file': segment_file,
            'start': segment['start'],
            'end': segment['end'],
            'text': segment['text'],
            'index': i
        })
    
    return audio_segments

def translate_and_generate_audio(segments, temp_dir, target_language="zh-CN", progress_bar=None):
    """Translate text segments and generate audio using gTTS"""
    
    # Language mapping for translation and TTS
    language_config = {
        'zh-CN': {'name': 'Chinese (Simplified)', 'trans': 'zh-CN', 'tts': 'zh-CN'},
        'zh-TW': {'name': 'Chinese (Traditional)', 'trans': 'zh-TW', 'tts': 'zh-TW'},
        'es': {'name': 'Spanish', 'trans': 'es', 'tts': 'es'},
        'fr': {'name': 'French', 'trans': 'fr', 'tts': 'fr'},
        'de': {'name': 'German', 'trans': 'de', 'tts': 'de'},
        'it': {'name': 'Italian', 'trans': 'it', 'tts': 'it'},
        'pt': {'name': 'Portuguese (Brazilian)', 'trans': 'pt', 'tts': 'pt-br'},
        'ja': {'name': 'Japanese', 'trans': 'ja', 'tts': 'ja'},
        'ko': {'name': 'Korean', 'trans': 'ko', 'tts': 'ko'},
        'ru': {'name': 'Russian', 'trans': 'ru', 'tts': 'ru'},
        'ar': {'name': 'Arabic', 'trans': 'ar', 'tts': 'ar'},
        'hi': {'name': 'Hindi', 'trans': 'hi', 'tts': 'hi'},
        'th': {'name': 'Thai', 'trans': 'th', 'tts': 'th'},
        'vi': {'name': 'Vietnamese', 'trans': 'vi', 'tts': 'vi'},
        'nl': {'name': 'Dutch', 'trans': 'nl', 'tts': 'nl'},
        'pl': {'name': 'Polish', 'trans': 'pl', 'tts': 'pl'},
        'tr': {'name': 'Turkish', 'trans': 'tr', 'tts': 'tr'},
        'sv': {'name': 'Swedish', 'trans': 'sv', 'tts': 'sv'},
        'da': {'name': 'Danish', 'trans': 'da', 'tts': 'da'},
        'no': {'name': 'Norwegian', 'trans': 'no', 'tts': 'no'}
    }
    
    config = language_config.get(target_language, language_config['zh-CN'])
    target_lang = config['trans']
    tts_lang = config['tts']
    
    translator = GoogleTranslator(source='en', target=target_lang)
    translated_audio_segments = []
    
    for i, segment in enumerate(segments):
        if progress_bar:
            progress_bar.progress((i + 1) / len(segments))
            
        text_to_translate = segment['text'].strip()
        
        if not text_to_translate or len(text_to_translate) < 2:
            continue
            
        # Translate text with retry logic
        max_retries = 3
        translated_text = text_to_translate
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(2)
                
                translated_text = translator.translate(text_to_translate)
                if translated_text and translated_text != text_to_translate:
                    break
                else:
                    raise Exception("Translation failed")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    translator = GoogleTranslator(source='en', target=target_lang)
                    time.sleep(3)
                else:
                    translated_text = text_to_translate
        
        # Generate translated speech
        try:
            tts = gTTS(text=translated_text, lang=tts_lang, slow=False)
            audio_file = os.path.join(temp_dir, f"translated_segment_{i:04d}.mp3")
            tts.save(audio_file)
            
            # Convert to wav and adjust duration
            wav_file = os.path.join(temp_dir, f"translated_segment_{i:04d}.wav")
            translated_audio = AudioSegment.from_mp3(audio_file)
            
            # Calculate target duration and adjust
            target_duration = (segment['end'] - segment['start']) * 1000
            current_duration = len(translated_audio)
            
            if current_duration > target_duration * 1.2:
                speed_factor = current_duration / target_duration
                translated_audio = translated_audio.speedup(playback_speed=speed_factor)
            elif current_duration < target_duration * 0.8:
                speed_factor = target_duration / current_duration
                translated_audio = translated_audio.speedup(playback_speed=1/min(speed_factor, 1.3))
            
            # Ensure exact fit
            if len(translated_audio) > target_duration:
                translated_audio = translated_audio[:int(target_duration)]
            elif len(translated_audio) < target_duration:
                silence_needed = int(target_duration - len(translated_audio))
                silence = AudioSegment.silent(duration=silence_needed)
                translated_audio = translated_audio + silence
            
            translated_audio.export(wav_file, format="wav")
            
            translated_audio_segments.append({
                'file': wav_file,
                'start': segment['start'],
                'end': segment['end'],
                'translated_text': translated_text,
                'index': i
            })
            
            os.remove(audio_file)
            
        except Exception as e:
            st.warning(f"Failed to generate audio for segment {i+1}: {str(e)}")
            continue
        
        # Rate limiting
        if (i + 1) % 3 == 0:
            time.sleep(1)
    
    return translated_audio_segments

def combine_translated_audio_segments(translated_segments, original_duration, temp_dir):
    """Combine translated audio segments into a single audio track"""
    duration_ms = int(original_duration * 1000)
    combined_audio = AudioSegment.silent(duration=duration_ms)
    
    for segment in translated_segments:
        start_ms = int(segment['start'] * 1000)
        translated_audio = AudioSegment.from_wav(segment['file'])
        combined_audio = combined_audio.overlay(translated_audio, position=start_ms)
    
    combined_file = os.path.join(temp_dir, "combined_translated_audio.wav")
    combined_audio.export(combined_file, format="wav")
    
    return combined_file

def create_video_with_translated_audio(original_video, translated_audio_file, output_video):
    """Replace original audio with translated audio in the video"""
    cmd = [
        'ffmpeg',
        '-i', original_video,
        '-i', translated_audio_file,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-shortest',
        '-y',
        output_video
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to create video: {e}")
        return False

def get_binary_file_downloader_html(bin_file, file_label='File'):
    """Generate download link for binary file"""
    with open(bin_file, 'rb') as f:
        data = f.read()
    bin_str = base64.b64encode(data).decode()
    href = f'<a href="data:application/octet-stream;base64,{bin_str}" download="{os.path.basename(bin_file)}">Download {file_label}</a>'
    return href

# Main Streamlit App
def main():
    st.markdown("<h1 class='main-header'>🌍 Universal Video Translator</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>Translate video audio from English to 20+ languages using AI</p>", unsafe_allow_html=True)
    
    # Features section
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class='feature-box'>
            <h4>🌍 Multi-Language</h4>
            <p>Translate to 20+ languages including Chinese, Spanish, German & more</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class='feature-box'>
            <h4>🤖 AI Powered</h4>
            <p>Uses OpenAI Whisper & Google Translate</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class='feature-box'>
            <h4>🎵 Natural Speech</h4>
            <p>High-quality text-to-speech in native accent</p>
        </div>
        """, unsafe_allow_html=True)
    
    # Check dependencies
    if not check_dependencies():
        st.error("FFmpeg is not installed. Please install FFmpeg to use this application.")
        st.stop()
    
    # Configuration section
    st.header("Configuration")
    col1, col2 = st.columns(2)
    
    with col1:
        # Language selection with proper mapping
        language_options = {
            'Chinese (Simplified) - 简体中文': 'zh-CN',
            'Chinese (Traditional) - 繁體中文': 'zh-TW',
            'Spanish - Español': 'es',
            'French - Français': 'fr',
            'German - Deutsch': 'de',
            'Italian - Italiano': 'it',
            'Portuguese (Brazilian) - Português': 'pt',
            'Japanese - 日本語': 'ja',
            'Korean - 한국어': 'ko',
            'Russian - Русский': 'ru',
            'Arabic - العربية': 'ar',
            'Hindi - हिन्दी': 'hi',
            'Thai - ไทย': 'th',
            'Vietnamese - Tiếng Việt': 'vi',
            'Dutch - Nederlands': 'nl',
            'Polish - Polski': 'pl',
            'Turkish - Türkçe': 'tr',
            'Swedish - Svenska': 'sv',
            'Danish - Dansk': 'da',
            'Norwegian - Norsk': 'no'
        }
        
        selected_language = st.selectbox(
            "Target Language",
            list(language_options.keys()),
            help="Choose the language you want to translate the audio to"
        )
        target_language = language_options[selected_language]
    
    with col2:
        whisper_model = st.selectbox(
            "Whisper Model",
            ["tiny", "base", "small", "medium"],
            index=1,
            help="Larger models are more accurate but slower"
        )
    
    # File upload section
    st.header("Upload Video")
    uploaded_file = st.file_uploader(
        "Choose an MP4 video file",
        type=['mp4'],
        help="Upload your video file (MP4 format only)"
    )
    
    if uploaded_file is not None:
        # Display video info
        st.success(f"✅ Video uploaded: {uploaded_file.name} ({uploaded_file.size / (1024*1024):.1f} MB)")
        
        # Process button
        if st.button("🚀 Start Translation", type="primary"):
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Save uploaded file
                    input_video_path = os.path.join(temp_dir, uploaded_file.name)
                    with open(input_video_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    # Progress tracking
                    progress_container = st.container()
                    with progress_container:
                        st.info("🔄 Starting translation process...")
                        
                        # Step 1: Transcription
                        st.info("🎤 Transcribing audio...")
                        model = whisper.load_model(whisper_model)
                        result = model.transcribe(
                            input_video_path,
                            task="transcribe",
                            language="en",
                            fp16=False
                        )
                        
                        # Get video duration
                        cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
                               '-of', 'default=noprint_wrappers=1:nokey=1', input_video_path]
                        duration_result = subprocess.run(cmd, capture_output=True, text=True)
                        original_duration = float(duration_result.stdout.strip())
                        
                        st.success(f"✅ Found {len(result['segments'])} speech segments ({original_duration:.1f}s video)")
                        
                        # Step 2: Audio extraction
                        st.info("🔧 Extracting audio segments...")
                        audio_segments = extract_audio_segments(input_video_path, result["segments"], temp_dir)
                        
                        # Step 3: Translation and TTS
                        language_name = selected_language.split(' - ')[0]
                        st.info(f"🌍 Translating to {language_name} and generating audio...")
                        progress_bar = st.progress(0)
                        translated_segments = translate_and_generate_audio(
                            audio_segments, temp_dir, target_language, progress_bar
                        )
                        
                        if translated_segments:
                            # Step 4: Combine audio
                            st.info("🎵 Combining audio segments...")
                            combined_audio = combine_translated_audio_segments(
                                translated_segments, original_duration, temp_dir
                            )
                            
                            # Step 5: Create final video
                            st.info("🎬 Creating final video...")
                            base_name = uploaded_file.name.rsplit(".", 1)[0]
                            language_suffix = target_language.replace('-', '_')
                            output_video = os.path.join(temp_dir, f"{base_name}_{language_suffix}_audio.mp4")
                            
                            success = create_video_with_translated_audio(
                                input_video_path, combined_audio, output_video
                            )
                            
                            if success and os.path.exists(output_video):
                                st.markdown("""
                                <div class='success-box'>
                                    <h4>🎉 Translation Complete!</h4>
                                    <p>Your video has been successfully translated.</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                # Display results
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric("Original Duration", f"{original_duration:.1f}s")
                                    st.metric("Segments Processed", len(translated_segments))
                                
                                with col2:
                                    st.metric("Target Language", language_name)
                                    st.metric("File Size", f"{os.path.getsize(output_video) / (1024*1024):.1f} MB")
                                
                                # Download button
                                with open(output_video, "rb") as file:
                                    st.download_button(
                                        label=f"⬇️ Download {language_name} Video",
                                        data=file.read(),
                                        file_name=f"{base_name}_{language_suffix}_audio.mp4",
                                        mime="video/mp4",
                                        type="primary"
                                    )
                                
                                # Sample translations preview
                                if st.expander("📝 View Sample Translations"):
                                    for i, segment in enumerate(translated_segments[:5]):  # Show first 5
                                        original_text = next(
                                            (s['text'] for s in result['segments'] if s.get('start') == segment['start']), 
                                            "Original text not found"
                                        )
                                        st.write(f"**Segment {i+1}:**")
                                        st.write(f"🇺🇸 Original: {original_text.strip()}")
                                        st.write(f"🌍 {language_name}: {segment['translated_text']}")
                                        st.write("---")
                            
                            else:
                                st.error("❌ Failed to create the final video. Please try again.")
                        else:
                            st.error("❌ No translated audio segments were generated. Please check your video.")
            
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                st.error("Please try again or contact support if the issue persists.")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 1rem;'>
        <p>Built with ❤️ using Streamlit, OpenAI Whisper, Google Translate & gTTS</p>
        <p><strong>Supported Languages:</strong> Chinese (Simplified & Traditional), Spanish, French, German, Italian, Portuguese, Japanese, Korean, Russian, Arabic, Hindi, Thai, Vietnamese, Dutch, Polish, Turkish, Swedish, Danish, Norwegian</p>
        <p><small>⚠️ Note: Large videos may take several minutes to process</small></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
