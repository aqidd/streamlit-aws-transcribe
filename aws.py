import requests
import streamlit as st
import boto3
from botocore.exceptions import ClientError
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
        LanguageCode='id-ID',  # Bahasa Indonesia
        Settings={
            'ShowSpeakerLabels': True,
            'MaxSpeakerLabels': 2,  # Adjust this number based on expected number of speakers
            'ChannelIdentification': False
        }
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
        transcript = ""
        combined_segments = []
        current_segment = None

        for segment in transcript_json['results']['audio_segments']:
            if current_segment is None:
                current_segment = segment
            else:
                current_end_time = float(current_segment['end_time'])
                next_start_time = float(segment['start_time'])
                
                if next_start_time - current_end_time < 0.5:
                    current_segment['end_time'] = segment['end_time']
                    current_segment['transcript'] += ' ' + segment['transcript']
                else:
                    combined_segments.append(current_segment)
                    current_segment = segment

        if current_segment:
            combined_segments.append(current_segment)

        for segment in combined_segments:
            start_time = float(segment['start_time'])
            end_time = float(segment['end_time'])
            content = segment['transcript']
            
            # Split the content if it contains a question mark
            if '?' in content:
                parts = content.split('?')
                for i, part in enumerate(parts):
                    if i < len(parts) - 1:
                        part += '?'
                    if part.strip():
                        segment_duration = end_time - start_time
                        part_start_time = start_time + (i * segment_duration / len(parts))
                        part_end_time = start_time + ((i + 1) * segment_duration / len(parts))
                        transcript += f"({part_start_time:.2f} - {part_end_time:.2f}): {part.strip()}  \n"
            else:
                transcript += f"({start_time:.2f} - {end_time:.2f}): {content}  \n"        
        return transcript
    else:
        return "Transcription failed"


def process_transcription(transcript):
    # Create a Bedrock Runtime client in the AWS Region you want to use.
    client = boto3.client("bedrock-runtime", region_name="ap-northeast-1")

    # Set the model ID, e.g., Titan Text Premier.
    model_id = "anthropic.claude-v2:1"

    st.subheader("Ringkasan dengan AI")
    prompt = """Dari transkrip di atas, berikan kesimpulan dengan format sebagai berikut:

    Keluhan Utama : <keluhan pasien waktu datang ke dokter>

    Diagnosa: <diagnosa pasien>

    ICD10: <ICD10 code berdasarkan diagnosa>

    Layanan / Tindakan: <layanan yang diberikan dokter dan/atau tindakan yang dilakukan ke pasien>

    Status Kesadaran: <pilih di antara Compos Mentis, Somnolence, Sopor, Coma>

    Status Pulang: <pilih di antara Berobat Jalan, Sehat, Rujuk, Meninggal>"""

    # Start a conversation with the user message.
    user_message = f"""Meeting transcript: 
    {transcript}
    
    {prompt}
    """
    conversation = [
        {
            "role": "user",
            "content": [{"text": user_message}],
        }
    ]

    try:
        # Send the message to the model, using a basic inference configuration.
        response = client.converse(
            modelId=model_id,
            messages=conversation,
            inferenceConfig={"maxTokens":4096,"stopSequences":["User:"],"temperature":0,"topP":1},
            additionalModelRequestFields={}
        )

        # Extract and print the response text.
        response_text = response["output"]["message"]["content"][0]["text"]
        st.write(response_text)

    except (ClientError, Exception) as e:
        st.error(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        exit(1)


st.title('Asisten Pintar: Speech to Text')

# Option to record audio using streamlit-mic-recorder
st.header("Record Audio:")
st.write("Press start recording to begin and press stop to finish. Wait for the transcription to complete after pressing stop.")

wav_audio_data = st_audiorec()

if wav_audio_data is not None:
    st.audio(wav_audio_data, format='audio/wav')

with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
    if wav_audio_data is not None:
        temp_file.write(wav_audio_data)
        temp_file_path = temp_file.name
        st.success(f"Audio saved to {temp_file_path}")
        file_format = temp_file.name.split('.')[-1]
        st.write("Processing transcription...")
        transcript = transcribe_audio(temp_file, file_format)
        st.subheader("Transcription Result:")
        st.write(transcript)
        process_transcription(transcript)

st.header("Upload file:")
st.write("Upload an audio file (.wav, .mp3, .m4a) to be transcribed.")
# Option to upload an audio file
uploaded_file = st.file_uploader("Upload an audio file", type=['wav', 'mp3', 'm4a'])

if uploaded_file is not None:
    file_format = uploaded_file.name.split('.')[-1]
    st.write("Processing transcription...")
    transcript = transcribe_audio(uploaded_file, file_format)
    st.subheader("Transcription Result:")
    st.write(transcript)
    process_transcription(transcript)
