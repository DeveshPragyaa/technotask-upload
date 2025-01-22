import requests
import json
import os
import re
import time
from datetime import datetime
from requests.auth import HTTPBasicAuth

def get_transcription_files(subscription_key, transcription_id, region):
    url = f"https://{region}.api.cognitive.microsoft.com/speechtotext/v3.2/transcriptions/{transcription_id}/files"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Accept": "application/json"
    }
    
    all_files = [] 
    while url:
        response = requests.get(url, headers=headers)
        print(f"Response status: {response.status_code}") 
        if response.status_code == 200:
            data = response.json()
            all_files.extend(data.get('values', [])) 
            url = data.get('@nextLink') 
        else:
            print(f"Failed to retrieve files. Status Code: {response.status_code}")
            print(response.json())
            return None

    return all_files  
def filter_existing_files(content_urls, directory="transcript_eng_1"):
    remaining_urls = []

    for url in content_urls:
        filename = url.split('/technotask/')[-1]

        file_path = os.path.join(directory, filename)
        if not os.path.exists(file_path):  
            remaining_urls.append(url)
        else:
            print(f"File {filename} exists. Removing URL: {url}")

    return remaining_urls
def create_transcription(subscription_key, region, content_urls, locale, diarization):
    print(f"Creating transcription for {len(content_urls)} audio files.")

    url = f"https://{region}.api.cognitive.microsoft.com/speechtotext/v3.2/transcriptions"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
        "Content-Type": "application/json"
    }
    data = {
        "displayName": "Batch Transcription",
        "contentUrls": filter_existing_files(content_urls),
        "locale": locale,
        "properties": {
            "diarizationEnabled": diarization,
            "wordLevelTimestampsEnabled": True
        }
    }
    response = requests.post(url, headers=headers, json=data)
    print(f"Transcription response: {response.status_code}, {response.text}")
    return response.json()

def check_transcription_status(transcription_url, subscription_key):
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key
    }
    while True:
        response = requests.get(transcription_url, headers=headers)
        status_info = response.json()
        status = status_info.get('status')
        print(f"Current transcription status: {status}")
        if status == 'Succeeded':
            return status_info
        elif status in ['NotStarted']:
            print("Transcription has not started or failed. Retrying...")
            time.sleep(5)  
        elif status == 'Failed':
            print("Failed due to : ",status_info)
            break
        else:
            print("Transcription is still in progress. Waiting...")
            time.sleep(10) 

def extract_content_urls_and_save_to_file(folder_name, files):
    print(f"Extracting content URLs and saving to files. Total files: {len(files)}")
    os.makedirs(folder_name, exist_ok=True)

    for idx, file in enumerate(files):
        if 'links' in file and 'contentUrl' in file['links']:
            audio_url = file['links']['contentUrl']
            print(f"Processing audio URL: {audio_url}")
            res = requests.get(audio_url).json()
            print("Response : ",res)  
            audio_url = res.get('source') 
            print("Audio : ",audio_url)
            if audio_url is None:
                print("No source URL found for audio. Skipping this file.")
                continue
            if "report.json" in audio_url:
                print(f"Skipping report.json file: {audio_url}")
                continue
            ordered_transcripts = []

            for phrase in res.get('recognizedPhrases', []):
                channel = phrase.get('speaker', 1)  
                if phrase.get('nBest'):
                    transcript = phrase['nBest'][0].get('display', ' ')
                    if transcript:
                        ordered_transcripts.append(f"Speaker {channel}: {transcript}")

            if ordered_transcripts:  
                url_path = audio_url.split('/')[-1].split('?')[0]
                print("Audio URL : ", url_path)
                file_path = os.path.join(folder_name, f"{url_path}.txt")
                
                print(f"Saving combined transcription to: {file_path}")
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(f"Audio URL: {audio_url}\n\n") 
                        for transcript in ordered_transcripts:
                            f.write(f"{transcript}\n")
                        print(f"Successfully saved combined transcription for {audio_url}")
                except Exception as e:
                    print(f"Failed to save combined transcription file: {e}")
            else:
                print("No valid recognized phrases found. Skipping saving the transcription.")


def summarize_transcript(transcript, prompt):
    endpoint = "https://swedencentral.api.cognitive.microsoft.com/openai/deployments/pragyaaGPT4o/chat/completions?api-version=2024-02-15-preview"
    key = "6424c639f54c46b88f7e8dcc512dcd70"
    retries = 0
    max_retries = 4
    full_prompt = f"{prompt}\nTranscription: {transcript}\nSummary: "

    payload = {
        "messages": [
            {"role": "system", "content": "You are a Summarization assistant. You need to summarize the Transcript into a single paragraph. Always start with 'Call discusses' or 'Call explains' "},
            {"role": "user", "content": full_prompt}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": key
    }
    while retries < max_retries:
        response = requests.post(endpoint, headers=headers, json=payload)
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(content)
            return content
        elif response.status_code == 429:
            retry_delay = int(response.headers.get('Retry-After', 40)) 
            print(f"Error 429: Rate limit exceeded. Retrying in {retry_delay} seconds...")
            retries += 1
            time.sleep(retry_delay)

        
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None

def evaluate_transcript(transcript, prompt, max_retries=4):
    endpoint = "https://swedencentral.api.cognitive.microsoft.com/openai/deployments/pragyaaGPT4o/chat/completions?api-version=2024-02-15-preview"
    key = "6424c639f54c46b88f7e8dcc512dcd70"

    full_prompt = f"Be quite lenient in terms of giving marks. You would be evaluating only the given transcript of the call. {prompt}\n{transcript}"

    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful evaluation assistant. Be quite lenient in terms of giving marks."},
            {"role": "user", "content": full_prompt}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": key
    }

    retries = 0
    while retries < max_retries:
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            json_content = re.search(r'(\{.*\})', content, re.DOTALL)
            try:
                if json_content:
                    return json_content.group(1).strip()  
                else:
                    return json.dumps(content, indent=4) 
            except Exception as JSONDecodeError:
                print(f"Error decoding JSON: {JSONDecodeError}, passing through another prompt")
                rectified_json = rectify_json(content)
                if rectified_json:
                    return rectified_json
                return None
        elif response.status_code == 429:
            retry_delay = int(response.headers.get('Retry-After', 40)) 
            print(f"Error 429: Rate limit exceeded. Retrying in {retry_delay} seconds...")
            retries += 1
            time.sleep(retry_delay)
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None
    
    print("Max retries reached. Unable to get a response.")
    return None

def rectify_json(eval, max_retries=4):
    endpoint = "https://swedencentral.api.cognitive.microsoft.com/openai/deployments/pragyaaGPT4o/chat/completions?api-version=2024-02-15-preview"
    key = "6424c639f54c46b88f7e8dcc512dcd70"

    full_prompt = f"Only give JSON Output. Rectify the given JSON structure. There may be any mistake. Check if braces are proper, semicolons are proper. Check if it is proper JSON structure. Incorrect structure : {eval}"

    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful JSON creator/rectifier agent."},
            {"role": "user", "content": full_prompt}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "api-key": key
    }

    retries = 0
    while retries < max_retries:
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code == 200:
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            
            json_content = re.search(r'(\{.*\})', content, re.DOTALL)

            if json_content:
                return json_content.group(1).strip()  
            else:
                return json.dumps(content, indent=4) 
        elif response.status_code == 429:
            retry_delay = int(response.headers.get('Retry-After', 40)) 
            print(f"Error 429: Rate limit exceeded. Retrying in {retry_delay} seconds...")
            retries += 1
            time.sleep(retry_delay)
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None
    
    print("Max retries reached. Unable to get a response.")
    return None
def prompts(transcript):
    prompt1 = """
    Be as liberal as possible while giving marks. Don't give too low marks at any cost.
    You are evaluating transcript. You need to give score between 4-10. Just give the number so that can be converted to integer
    evaluate the given call transcript in point 1 below, based on the following ten parameters only mentioned in point 2 below (soft skills to be evaluated and criteria specified for each soft skill) and not for any other parameter. Provide the response in the format specified in point 3 only. 
        Soft skills to be evaluated:
    Parameter 1: Greet & Call Opening
    Criteria:

    Greet the customer with Good morning, Good afternoon, or Hello, etc.
    Introduce yourself and mention the brand (if possible).
    For IVR systems: The IVR should greet the customer, e.g., “Welcome to [Brand Name], how can I help you today?”
    Evaluation:
    Basic greetings like “Hello” are fine. No need for a detailed self-introduction or personalized greeting in the IVR.
    Parameter 2: Active Listening / Acknowledgement
    Criteria:

    Acknowledge the customer with phrases like “OK,” “Sure,” “Alright,” etc.
    Listen to the customer and respond appropriately.
    No unnecessary repetition or interruptions.
    For IVR systems: Acknowledge customer choices (e.g., “You selected option 2”).
    Evaluation:
    Simple, clear responses are sufficient for both agents and IVRs.
    No need for long conversations, just clear acknowledgments after customer inputs.
    Parameter 3: Empathy / Apology / Power Words
    Criteria:

    Use phrases like “I understand,” “Sorry for the inconvenience,” or “Thank you for your patience.”
    For IVR systems: Use basic empathy, e.g., “We’re sorry for the wait.”
    Evaluation:
    The IVR can use simple, empathetic phrases. No need for overly emotional or elaborate statements.
    Parameter 4: Probing
    Criteria:

    Ask relevant questions to understand the issue better.
    For IVR systems: The system can ask simple questions like “Press 1 for billing” or “Press 2 for support.”
    Evaluation:
    For agents: Simple questions to get more details are fine.
    For IVR: Closed-ended questions work perfectly, no need for deep probing.
    Parameter 5: Hold Procedure
    Criteria:

    Ask permission before placing the call on hold.
    Inform the customer why they’re on hold.
    For IVR systems: If transferring the call, inform the customer, e.g., “Please hold for a moment.”
    Evaluation:
    If the customer is placed on hold, just give them a simple reason and avoid doing it too many times.
    IVRs should inform the customer about any wait or transfer.
    Parameter 6: Dead Air / Fillers / Jargon
    Criteria:

    Engage in conversation without long silences or unnecessary fillers.
    Avoid using technical jargon.
    For IVR systems: No long pauses, and use simple language.
    Evaluation:
    For agents: Keep the conversation going, but no need to fill every pause with extra words.
    For IVR: Respond quickly after customer input and use easy-to-understand language.
    Parameter 7: Appreciate Customers
    Criteria:

    Appreciate the customer for their patience or action.
    For IVR systems: Use phrases like “Thank you for your patience.”
    Evaluation:
    Simple appreciation goes a long way, like “Thank you for holding” or “Thank you for choosing [Brand Name].”
    Parameter 8: Confidence / Fumbling
    Criteria:

    Avoid hesitation or fumbling during the conversation.
    For IVR systems: The system should speak clearly and at a steady pace.
    Evaluation:
    For agents: Confidence in speech is important, but some pauses or rephrasing are okay.
    For IVR: It should speak clearly and smoothly, but minor pauses are acceptable.
    Parameter 9: Closing of the Call
    Criteria:

    Summarize the call briefly.
    Offer further assistance.
    For IVR systems: The IVR can simply confirm the next steps, e.g., “You will now be transferred to a representative.”
    Evaluation:
    For agents: A quick summary and offer to help is enough.
    For IVR: A simple confirmation of action is all that’s needed.
    Parameter 10: Tone of Voice (Polite / Courteous / Energetic) / Speech Clarity
    Criteria:

    The tone should be friendly, polite, and clear.
    Avoid rude or sarcastic tones.
    For IVR systems: Use a neutral, friendly tone.
    Evaluation:
    For agents: The tone should be professional, but not overly energetic or formal.
    For IVR: Clear and neutral tone with no need for high energy or excitement.
            
            Format:
            {
            "Greet_or_Call_Opening": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Active_Listening": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Empathy": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Probing": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Hold_Procedure": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Dead_Air_Fillers_and_Foghorns_Jargons": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Appreciate_Customers": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Confidence_Fumbling": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Closing_of_the_call": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" },
            "Tone_Of_Voice": { "Met":"[value]", "Score": "[value]", "Reasons": "[value]" }
            }            
        1.    Call transcript:
    """
    prompt2 = """
    another prompt:
    evaluate the given call transcript in point 1 below, 
    evaluate for campaign criteria specified in Point 2 and not for any other parameter. 
    Provide the response in the format specified in point 3 only. 
    Sentiment of the customer on the call [Happy/Unhappy/Neutral]. In the case of IVR, sentiment can be inferred from the clarity of instructions, available options, and if the customer’s potential needs are addressed (i.e., was the IVR providing useful, actionable information?).
    Customer issues or queries resolved or not [Yes/No/NA]. In case of IVR, this would involve checking if the system provided clear options for the user to resolve their query or if the issue could be addressed by following the instructions.
    Which Department is the call for [Department]. In case the IVR mentions a specific department or service type (like Returns, Refunds, Technical Support), use that information.

    2.	Campaign Criteria: Criteria for campaigns
        check for Sentiment of the customer on the call [Happy/ unhappy/ Neutral], Customer issues or queries resolved or not [Yes/ No/ NA], Which Deprartment is the call for [Department]
            Format:
            {
                "customer_sentiment":"[Happy/Unhappy/Neutral]",
                "customer_queries_resolved":"[Yes/No/NA]",
                "department_name":"[Any organization mentioned, try to interpret best possible if any organization is mentioned else say 'None']"

            }            
        1.    Call transcript:
    """
    prompt3  = """
    another prompt:
    Please give in the below format at any cost.
    You need to evaluate the given transcript of the audio.
    evaluate the given call transcript in point 1 below, evaluate for campaign criteria specified in Point 2 and not for any other parameter. 
        
        Provide the response in the format specified in point 2 only. 
        2.    Evaluate criteria:
        1.      escalation Criteria: Criteria for escalations. These are the only criteria for escalation and call should not be marked as Yes for Escalation if any one of these escalation criteria is not met.
        -    Customer upset, want to speak with higher authority, 
        -    Issue transferred to a supervisor, manager. 
        -    Shouting on call
        -    Arguments.
        -    Abusive on call
    2. Primary Criteria : Was the primary criteria related to Customer care (e.g., querying information, resolving issues through IVR such as refunds, orders, or returns)?
                If this primary criteria is not met, then the evaluation response for campaign criteria should be NA.
                If this primary criteria is met, proceed to evaluate the following:

        3.    If the primary criteria is met, please assess the following criteria:
                    Campaign Criteria: [Met/Not Met].
                    Campaign Criteria Reason: [Provide a reason for your assessment].
                    Customer frustration or wanting to speak with a higher authority: Did the customer indicate dissatisfaction or request to speak with an agent? [YES/NO].
                    Issue transferred to a supervisor/manager: Was the issue transferred to a live agent or higher authority during the IVR process? [YES/NO].
                    Shouting on call: Did the customer raise their voice, express frustration audibly, or seem agitated during the IVR interaction? [YES/NO].
                    Arguments: Were there any indications of an argument between the customer and the system (e.g., multiple attempts to resolve the same query)? [YES/NO].
                    Abusive language on call: Did the customer use abusive or offensive language during the IVR interaction? [YES/NO].
                    Incorrect information in IVR options: Did the IVR provide incorrect or misleading information that led to confusion? [YES/NO].
                    Inadequate IVR options: Did the IVR fail to provide enough options to resolve the customer's query effectively? [YES/NO].

            Format:
            {
            "escalation_call": { "met":"[YES/NO]", "reasons": "[value]" },
            "primary_criteria_check": { "met":"[Met/Not Met]", "reasons": "[value]" },
            "campaign_criteria": "[Met/Not Met]",
            "campaign_criteria_reason": "[value]",
            "is_customer_wants_to_speak_higher_authority": "[YES/NO]",
            "is_issue_transfered_to_supervisor_or_manager": "[YES/NO]",
            "is_customer_shouting_on_call": "[YES/NO]",
            "is_arguments": "[YES/NO]",
            "is_abusive_on_call": "[YES/NO]",
            "is_incorrect_or_wrong_test_price_or_wrong_test_amount_informed": "[YES/NO]",
            "is_wrong_test_informed": "[YES/NO]",
            "is_incorrect_ivr_instructions": "[YES/NO]",
            "is_customer_query_not_resolved_by_ivr": "[YES/NO]"

            }            
        1.    Call transcript:
    """
    
    eval_1 = evaluate_transcript(transcript, prompt1)
    eval_2 = evaluate_transcript(transcript, prompt2)
    eval_3 = evaluate_transcript(transcript, prompt3)

    return eval_1, eval_2, eval_3


def summary(transcript):
    prompt = """
    You are given Transcription of an audio. 
    The audio would be related to some Customer Service.
    Summarize this transcription based on it, and try to include important points in it. 
    If possible also try to check what user has pressed.
    The summary should be in 1 paragraph around 2-4 lines. Directly give the summary.
    In the summary start from 'The call appears to' or 'Call discusses'.
    """
    content = summarize_transcript(transcript, prompt)
    return content


def check_if_document_exists(filename, search_url):
    search_query = {
        "query": {
            "match": {
                "filename": filename
            }
        }
    }
    response = requests.get(search_url, json=search_query, auth=HTTPBasicAuth('admin', 'Threeguys01!'), verify=False)
    if response.status_code == 200:
        hits = response.json().get('hits', {}).get('hits', [])
        return len(hits) > 0, hits[0]['_id'] if hits else None
    else:
        print(f"Error checking document existence: {response.status_code}, Response: {response.text}")
        return False, None

def extract_transcription(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            transcription = ''.join(lines[1:]).strip() 
        return transcription if transcription else None
    except FileNotFoundError:
        return None

def extract_audio_url(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            for line in lines:
                if line.startswith('Audio URL:'):
                    return line.split('Audio URL:')[1].strip()
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def process_eval_data_1(eval_data_1, document):
    total_score = 0
    keys_to_process = [
        "Greet_or_Call_Opening",
        "Active_Listening",
        "Empathy",
        "Probing",
        "Hold_Procedure",
        "Dead_Air_Fillers",
        "Appreciate_Customers",
        "Confidence_Fumbling",
        "Closing_of_the_call",
        "Tone_Of_Voice"
    ]

    for key in keys_to_process:
        if key in eval_data_1:
            print(f"{key}_Met")
            document[f"{key}_Met"] = eval_data_1[key].get("Met", "")
            score = eval_data_1[key].get("Score", "0")
            print(score)
            document[f"{key}_Reasons"] = eval_data_1[key].get("Reasons", "")
            score = 0 if score in ['NA', 'N/A', 'Not Applicable'] else score
            score = int(score)
            document[f"{key}_Score"] = score
            total_score += score

    document["total_score"] = total_score
    return document

def process_eval_data_2(eval_data_2, document):
    document["customer_sentiment"] = eval_data_2.get("customer_sentiment", "")
    document["customer_queries_resolved"] = eval_data_2.get("customer_queries_resolved", "")
    document["department_name"] = eval_data_2.get("department_name", "")
    return document

def process_eval_data_3(eval_data_3, document):
    if "escalation_call" in eval_data_3:
        document["escalation_call_met"] = eval_data_3["escalation_call"].get("met", "")
        document["escalation_call_reasons"] = eval_data_3["escalation_call"].get("reasons", "")

    if "primary_criteria_check" in eval_data_3:
        document["primary_criteria_check_met"] = eval_data_3["primary_criteria_check"].get("met", "")
        document["primary_criteria_check_reasons"] = eval_data_3["primary_criteria_check"].get("reasons", "")

    document["campaign_criteria"] = eval_data_3.get("campaign_criteria", "")
    document["campaign_criteria_reason"] = eval_data_3.get("campaign_criteria_reason", "")
    document["is_customer_wants_to_speak_higher_authority"] = eval_data_3.get("is_customer_wants_to_speak_higher_authority", "")
    document["is_incorrect_ivr_instructions"] = eval_data_3.get("is_incorrect_ivr_instructions", "")
    document["is_customer_query_not_resolved_by_ivr"] = eval_data_3.get("is_customer_query_not_resolved_by_ivr", "")
    return document


def document_formation(file):
    file_eng = os.path.join("transcript_eng_1", file)
    print(file_eng)
    transcript = extract_transcription(file_eng)
    print(transcript)
    eval1, eval2, eval3 = prompts(transcript)
    eval1 = json.loads(eval1)
    eval2 = json.loads(eval2)
    eval3 = json.loads(eval3)
    
    document = {
        'audio_url':extract_audio_url(file_eng),
        'filename':file.split('.txt')[0],
        'date':datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'timestamp':datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        'transcription_eng':transcript,
        'transcript_summary':summary(transcript),
    }
    document |= process_eval_data_1(eval1, {})
    document |= process_eval_data_2(eval2, {})
    document |= process_eval_data_3(eval3, {})
    return document

def index(document, update_url, search_url, index_url):
    filename = document['filename']
    print(filename)
    exists, doc_id = check_if_document_exists(filename, search_url)
    if exists:
        response = requests.post(update_url + doc_id, json={"doc": document}, auth=HTTPBasicAuth('admin', 'Threeguys01!'), verify=False)
        if response.status_code == 200:
            print(f"Document updated successfully: {filename}")
        else:
            print(f"Failed to update document: {filename}. Status code: {response.status_code}")
    else:
        response = requests.post(index_url, json=document, auth=HTTPBasicAuth('admin', 'Threeguys01!'), verify=False)
        if response.status_code == 201:
            print(f"Document indexed successfully: {filename}")
        else:
            print(f"Failed to index document: {filename}. Status code: {response.status_code}")
