import os
import urllib3
from azure.storage.blob import BlobServiceClient
from functions import create_transcription, check_transcription_status, extract_transcription, get_transcription_files, extract_content_urls_and_save_to_file, document_formation, index
from datetime import datetime, timedelta
import pytz
import time as time_module
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load variables from environment
INDEX = os.getenv("INDEX")
URL = os.getenv("URL")
PORT_NEW = os.getenv("PORT_NEW")
index_url = f'https://{URL}:{PORT_NEW}/{INDEX}/_doc/'
search_url = f'https://{URL}:{PORT_NEW}/{INDEX}/_search'
delete_index_url = f'https://{URL}:{PORT_NEW}/{INDEX}'
update_url = f'https://{URL}:{PORT_NEW}/{INDEX}/_update/'

container_name = os.getenv("CONTAINER_NAME")
subscription_key = os.getenv("SUBSCRIPTION_KEY")
region = os.getenv("REGION")
locale = os.getenv("LOCALE")
folder_name = os.getenv("FOLDER_NAME")
diarization = os.getenv("DIARIZATION") == "True"

connection_string = os.getenv("CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(connection_string)
container_client = blob_service_client.get_container_client(container_name)

def transcribe(content_urls, path="transcript_eng_1"):
    transcription_response = create_transcription(subscription_key, region, content_urls, locale, diarization)
    transcription_url = transcription_response['self']
    final_status_info = check_transcription_status(transcription_url, subscription_key)
    
    if final_status_info['status'] == 'Succeeded':
        transcription_id = transcription_url.split('/')[-1]
        files = get_transcription_files(subscription_key, transcription_id, region)
        if files:
            extract_content_urls_and_save_to_file(folder_name, files)
            update_data(path)
        else:
            print("No transcription files found.")
    elif final_status_info['status'] == 'Failed':
        print("Transcription status failed.")
    else:
        print("Transcription did not succeed.")

def update_data(path):
    for file in os.listdir(path):
        print("File : ", file)
        document = document_formation(file)
        index(document, update_url, search_url, index_url)
