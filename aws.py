import requests
import streamlit as st
import boto3
import time
from dotenv import load_dotenv
import os
import tempfile
from st_audiorec import st_audiorec

# Load AWS credentials from .env file
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION')
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET')

def transcribe_audio(file, file_format):
    transcribe = boto3.client(
        'transcribe',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
    job_name = f"transcribe-job-{int(time.time())}"
    job_uri = f"s3://{AWS_S3_BUCKET}/{file.name}"

    # Upload file to S3 bucket
    s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    if isinstance(file, tempfile._TemporaryFileWrapper):
        try:
            file.seek(0)
            s3.upload_fileobj(file, AWS_S3_BUCKET, file.name)
        finally:
            temp_file.close()
    else:
        # Jika file adalah UploadedFile, gunakan upload_fileobj
        s3.upload_fileobj(file, AWS_S3_BUCKET, file.name)

    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={'MediaFileUri': job_uri},
        MediaFormat=file_format,  # Pass the file format dynamically
        LanguageCode='id-ID'  # Bahasa Indonesia
    )

    while True:
        status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
            break
        time.sleep(15)
    
    if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
        transcript_file_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
        transcript_response = requests.get(transcript_file_uri)
        transcript_json = transcript_response.json()
        transcript = transcript_json['results']['transcripts'][0]['transcript']
        return transcript
    else:
        return "Transcription failed"

st.title('Asisten Pintar: Speech to Text')

# Option to record audio using streamlit-mic-recorder
st.header("Record Audio:")
st.write("Press start recording to begin and press stop to finish. Wait for the transcription to complete after pressing stop.")

wav_audio_data = st_audiorec()

if wav_audio_data is not None:
    st.audio(wav_audio_data, format='audio/wav')    
    st.write("Tipe data wav_audio_data:", type(wav_audio_data))

with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
    if wav_audio_data is not None:
        temp_file.write(wav_audio_data)
        temp_file_path = temp_file.name
        st.success(f"Audio saved to {temp_file_path}")
        file_format = temp_file.name.split('.')[-1]
        st.write("Processing transcription...")
        transcript = transcribe_audio(temp_file, file_format)
        st.write("Transcription Result:")
        st.write(transcript)

st.header("Upload file:")
st.write("Upload an audio file (.wav, .mp3, .m4a) to be transcribed.")
# Option to upload an audio file
uploaded_file = st.file_uploader("Upload an audio file", type=['wav', 'mp3', 'm4a'])

if uploaded_file is not None:
    file_format = uploaded_file.name.split('.')[-1]
    st.write("Processing transcription...")
    transcript = transcribe_audio(uploaded_file, file_format)
    st.write("Transcription Result:")
    st.write(transcript)