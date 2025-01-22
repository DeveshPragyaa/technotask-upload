from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse
from azure.storage.blob import BlobServiceClient
from typing import List
import os
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from final import transcribe
from datetime import datetime, timedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
CONTAINER_NAME = "technotask"

blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

def generate_sas_token(blob_name):

    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True), 
        expiry=datetime.utcnow() + timedelta(days=365 * 10) 
    )
    return sas_token

@app.post("/upload")
async def upload_files(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    uploaded_files = []
    content_urls = []
    filenames = []
    try:
        for file in files:
            file_content = await file.read()
            blob_client = container_client.get_blob_client(file.filename)
            blob_client.upload_blob(file_content, overwrite=True)

            sas_token = generate_sas_token(file.filename)

            content_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{file.filename}?{sas_token}"

            uploaded_files.append({
                "filename": file.filename,
            })
            content_urls.append(content_url)
            filenames.append(file.filename)
        print("Content URLs with SAS tokens:", content_urls)
        background_tasks.add_task(transcribe, content_urls)
        return JSONResponse(content={
            "message": "Files uploaded successfully",
            "files": uploaded_files,
        })

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
