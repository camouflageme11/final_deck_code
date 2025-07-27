# ----------- imports ---------------
from PIL import Image
import time
import googlemaps
from django.conf import settings
from io import BytesIO
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from google.cloud import vision
import feedparser
from google.cloud import translate_v2 as translate
import os
from urllib.parse import quote_plus
import requests
from django.http import JsonResponse
from datetime import datetime, timedelta
from django.shortcuts import render
import requests
import json
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import aiplatform
from google.oauth2 import service_account
from agenticai.vertex_client import query_vertex_ai
from PIL import Image
import json
import os
import json
import piexif
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from google.cloud import vision
#------------------------------------
import warnings
from django.views.decorators.csrf import csrf_exempt
warnings.simplefilter("ignore")
# -----------------------------------

#------------- global variables -------------
labels_found = {}
top_alerts = []
output_alerts = []
hindi_alerts = []
kannada_alerts = []
#------------- utility calls ---------

# initialise firebase app
cred = credentials.Certificate("./agenticai/firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
#-------------------------------------


#----------- utlity functions ------------

# insert data into db
def insert_data(agent_name, json_data, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now()
    doc_ref = db.collection('traffic_reports').document()
    doc_ref.set({
        'agent_name': agent_name,
        'json_data': json_data,
        'timestamp': timestamp
    })

    # print(f"Inserted data for agent: {agent_name} at {timestamp}")

# fetch data into db
def fetch_data(start_time, end_time):
    reports_ref = db.collection('traffic_reports')
    query = reports_ref.where('timestamp', '>=', start_time).where('timestamp', '<=', end_time)
    results = query.stream()
    data = []
    for doc in results:
        item = doc.to_dict()
        item['id'] = doc.id
        data.append(item)
    return data

# prompt vertex ai
def send_to_vertex(json_object):
    user_query = json_object.get("query", "")
    context_data = json_object.get("data", "")
    
    # Combine query and data
    prompt_text = f"{user_query}\n\n{context_data}"

    # Gemini expects structured input
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt_text}
                ]
            }
        ],
        "generationConfig": {
        "temperature": 0.2,        # Lower = more deterministic (0.0 to 1.0)
        "topP": 0.8,
        "topK": 40,
        "maxOutputTokens": 512     # Limit output length if needed
        }
    }

    result = query_vertex_ai(payload)

    return JsonResponse({"response": result})


@csrf_exempt  # Only for testing, remove or secure in production
def upload_image(request):
    if request.method == 'POST':
        image_file = request.FILES.get('image')
        if not image_file:
            return JsonResponse({'error': 'No image file provided'}, status=400)

        # Read image into Pillow
        try:
            image = Image.open(image_file)
        except Exception as e:
            return JsonResponse({'error': f'Invalid image: {str(e)}'}, status=400)

        description = request.POST.get('description', '')
        # Basic metadata
        metadata = {
            'format': image.format,
            'mode': image.mode,
            'size': image.size,
        }

        # Extract EXIF data if present
        exif_data = {}
        try:
            exif_raw = image._getexif()
            if exif_raw:
                for tag_id, value in exif_raw.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    exif_data[tag] = value
        except Exception as e:
            exif_data['error'] = f'Failed to extract EXIF data: {str(e)}'

        # Print metadata and EXIF data (for debugging)
        # print('Image Metadata:', metadata)
        # print('EXIF Data:', exif_data)

        global labels_found
        labels_found['metadata'] = metadata
        labels_found['exif_data'] = exif_data
        labels_found['description'] = description

        # Return metadata and EXIF data as JSON response
        return JsonResponse({
            'metadata': metadata,
            'exif_data': exif_data
        })

    return JsonResponse({'error': 'POST request required'}, status=405)

def _get_if_exist(data, key):
    return data[key] if key in data else None

def _convert_to_degrees(value):
    """Helper to convert GPS coordinates stored in EXIF to degrees in float."""
    d = value[0][0] / value[0][1]
    m = value[1][0] / value[1][1]
    s = value[2][0] / value[2][1]
    return d + (m / 60.0) + (s / 3600.0)

def extract_gps_info(exif_data):
    gps_info = {}
    gps_data = _get_if_exist(exif_data, 34853)  # GPSInfo tag id
    if not gps_data:
        return None

    # Map GPS tags to their names
    gps_tags = {}
    for key in gps_data.keys():
        decoded = ExifTags.GPSTAGS.get(key, key)
        gps_tags[decoded] = gps_data[key]

    try:
        lat = _convert_to_degrees(gps_tags['GPSLatitude'])
        if gps_tags.get('GPSLatitudeRef') != 'N':
            lat = -lat

        lon = _convert_to_degrees(gps_tags['GPSLongitude'])
        if gps_tags.get('GPSLongitudeRef') != 'E':
            lon = -lon

        gps_info['Latitude'] = lat
        gps_info['Longitude'] = lon
    except Exception:
        return None

    return gps_info

@csrf_exempt
def analyze_image_labels(request):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./agenticai/service_account.json"
    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']

        # Save the image to the current directory
        filename = image_file.name
        save_path = os.path.join(".", filename)
        with open(save_path, "wb") as f:
            for chunk in image_file.chunks():
                f.write(chunk)
        
        # After saving, read content for Vision API
        with open(save_path, "rb") as f:
            content = f.read()

        # Vision API call
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=content)
        response = client.label_detection(image=image)
        labels = [label.description for label in response.label_annotations]
        # print("Detected labels:", labels)
        return JsonResponse({'labels': labels})
    return JsonResponse({'error': 'No image uploaded or wrong method'}, status=400)

# GOOGLE RSS API

def scrape_google_news():
    query = quote_plus("Bengaluru traffic OR accident OR roadblock OR fire OR flood")
    url = f"https://news.google.com/rss/search?q={query}"
    feed = feedparser.parse(url)
    results = []
    for entry in feed.entries:
        results.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.published,
            "summary": entry.summary,
        })
    # print(f"🚨 Found {len(results)} Google News articles related to traffic:\n")
    return JsonResponse({"location": "Bengaluru", "articles": results})

# twitter data / mock data
def twitter_data_fetch():
    # Get the path of the current file's folder
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "twitter_data.json")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            twitter_data = json.load(f)
        # Now twitter_data contains the loaded JSON data as a dict
        return twitter_data
    except Exception as e:
        print(f"Error loading twitter_data.json: {e}")
        return None

def route_traffic(request):
    # Configure with your actual API key (store in settings.py)
    GMAPS_API_KEY = getattr(settings, 'GOOGLE_MAPS_API_KEY', 'AIzaSyAs4vL4I7vzGamP_WeGO1IaZE5kmisUcZE')
    
    # More specific Bangalore locations with landmarks
    routes = [
        ("Bangalore City Railway Station, Bangalore", "Vidhana Soudha, Bangalore"),
        ("Vidhana Soudha, Bangalore", "Cubbon Park, Bangalore"),
        ("Electronic City Metro Station, Bangalore", "Silk Board Junction, Bangalore"),
        ("Marathahalli Bridge, Bangalore", "KR Puram Railway Station, Bangalore"),
        ("MG Road Metro Station, Bangalore", "Koramangala Water Tank, Bangalore")
    ]
    
    traffic_data = []
    errors = []
    
    try:
        gmaps = googlemaps.Client(key="AIzaSyAs4vL4I7vzGamP_WeGO1IaZE5kmisUcZE")
        
        for start, end in routes:
            try:
                # Add delay between API calls to avoid rate limiting
                time.sleep(1)  
                
                now = datetime.now()
                directions = gmaps.directions(
                    start,
                    end,
                    mode="driving",
                    departure_time=now,
                    traffic_model="best_guess",
                    region="in"  # Focus on India
                )
                
                # Process successful response
                leg = directions[0]['legs'][0]
                delay_seconds = leg['duration_in_traffic']['value'] - leg['duration']['value']
                
                route_info = {
                    'route': f"{start.split(',')[0]} → {end.split(',')[0]}",
                    'distance': leg['distance']['text'],
                    'normal_time': leg['duration']['text'],
                    'traffic_time': leg['duration_in_traffic']['text'],
                    'delay_minutes': delay_seconds // 60,
                    'delay_seconds': delay_seconds % 60,
                    'status': 'success',
                    'start': start.split(',')[0].strip(),
                    'end': end.split(',')[0].strip()
                }
                traffic_data.append(route_info)
                
                # Print to console
                # print(f"\nRoute: {start} → {end}")
                # print(f"Distance: {route_info['distance']}")
                # print(f"Normal time: {route_info['normal_time']}")
                # print(f"Current traffic time: {route_info['traffic_time']}")
                # print(f"Delay: {route_info['delay_minutes']} min {route_info['delay_seconds']} sec")
                
            except Exception as e:
                error_msg = f"Error processing {start} → {end}: {str(e)}"
                errors.append(error_msg)
                print(error_msg)
                traffic_data.append({
                    'route': f"{start.split(',')[0]} → {end.split(',')[0]}",
                    'status': 'error',
                    'error': str(e),
                    'start': start.split(',')[0].strip(),
                    'end': end.split(',')[0].strip()
                })
                
    except Exception as e:
        errors.append(f"API connection error: {str(e)}")
        print(f"\nFATAL ERROR: {str(e)}")
    
    # Prepare context
    context = {
        'traffic_data': traffic_data,
        'errors': errors,
        'last_updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'success_count': len([x for x in traffic_data if x['status'] == 'success'])
    }
    
    return render(request, 'route_traffic.html', context)

#translator
def translate_text(text, target_language):
    """
    Translates the given text into the target language using Google Cloud Translate API.
    
    Args:
        text (str): The text to be translated.
        target_language (str): The language code to translate the text into (e.g., 'fr', 'hi', 'es').

    Returns:
        str: The translated text.
    """
    try:
        # Set the path to your service account key
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "./agenticai/service_account.json"
        
        # Initialize the Translate client
        client = translate.Client()
        
        # Perform translation
        result = client.translate(text, target_language=target_language)
        
        translated_text = result['translatedText']
        # print(f"Translated Text: {translated_text}")
        return translated_text
    except Exception as e:
        print(f"Translation failed: {e}")
        return None

def make_prompt(prompt, data_text=None):
    data = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"""{prompt}: data:{data_text}"""}]
            }
        ]
    }
    return data

#------------- The Master (Admin Agent) -------------------

def master_agent(request):
    
    # 1. The Listener
    twitter_data = twitter_data_fetch()
    google_news_data = scrape_google_news()
    
    # 2. The Judge
    combined = {}
    # Prefix Twitter data keys with 'twitter_' to avoid collisions
    for key, value in twitter_data.items():
        combined[f"twitter_{key}"] = value
    # Prefix Google news keys with 'google_news_' to avoid collisions
    for key, value in google_news_data.items():
        combined[f"google_news_{key}"] = value
    
    # Construct prompt
    make_judge_prompt = make_prompt(
        prompt=(
            "You are given a dataset containing news and tweets. "
            "Extract only the records that are relevant to traffic in Bengaluru. Do not change any contents "
            "For each relevant record, return:\n"
            "- reason: why it's related to traffic\n"
            "- latitude (if any)\n"
            "- longitude (if any)\n\n"
            "Respond only in this JSON format:\n"
            "[\n"
            "  {\n"
            "    \"reason\": \"<reason>\",\n"
            "    \"latitude\": <latitude>,\n"
            "    \"longitude\": <longitude>\n"
            "  }, ...\n"
            "]"
        ),
        data_text=json.dumps(combined, indent=2)
    )
    judge_output = send_to_vertex(make_judge_prompt)
    # print("Judge Output:", judge_output.content.decode('utf-8'))
    insert_data("judge", judge_output.content.decode('utf-8'))

    # 3. The Scanner
    global labels_found
    # print(labels_found)
    scanner_prompt = make_prompt(
        prompt=(
            "You are analyzing metadata and EXIF data extracted from an image file. "
            "Your task is to identify and extract only the information that is relevant to **traffic in Bengaluru**. "
            "From the given data, return records that suggest traffic congestion, road conditions, accidents, or any other traffic-related events.\n\n"
            "For each relevant entry, provide:\n"
            "- reason: Why it is relevant to Bengaluru traffic\n"
            "- latitude (if available)\n"
            "- longitude (if available)\n\n"
            "Return the result strictly in this JSON format:\n"
            "[\n"
            "  {\n"
            "    \"reason\": \"<reason>\",\n"
            "    \"latitude\": <latitude>,\n"
            "    \"longitude\": <longitude>\n"
            "  }\n"
            "]"
        ),
        data_text=json.dumps(labels_found, indent=4)
    )

    scanner_output = send_to_vertex(scanner_prompt)
    insert_data("scanner", scanner_output.content.decode('utf-8'))
    


    # 4. The Telescope
    # traffic --> route_traffic takes care
    # weather --> fetch_and_store_weather 

    # The guide
    # Fetch last 24 hours data from Firestore and sort by timestamp ascending
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    last_24h_data = fetch_data(start_time, end_time)
    # Convert Firestore timestamps to ISO strings for JSON serialization
    for item in last_24h_data:
        if 'timestamp' in item and hasattr(item['timestamp'], 'isoformat'):
            item['timestamp'] = item['timestamp'].isoformat()
        # Convert any bytes fields to strings for JSON serialization
        for k, v in item.items():
            if isinstance(v, bytes):
                try:
                    item[k] = v.decode('utf-8')
                except Exception:
                    item[k] = str(v)
    last_24h_data_sorted = sorted(last_24h_data, key=lambda x: x['timestamp'])
    # print("making guide prompt")
    # print("Last 24h data sorted:", json.dumps(last_24h_data_sorted, indent=4))
    guide_prompt = make_prompt(
        prompt=(
            "You are generating a structured traffic report for Bengaluru using data from multiple sources, including:\n"
            "1. Judge (news + Twitter relevance judgment)\n"
            "2. Scanner (image metadata and EXIF)\n"
            "3. Weather data\n"
            "4. Traffic route info\n\n"
            "Analyze the combined data and return a comprehensive report strictly in JSON format. For each entry, include:\n"
            "- category: (news, twitter, image, weather, route)\n"
            "- summary: A concise 15–30 word alert about the traffic situation\n"
            "- latitude (if available)\n"
            "- longitude (if available)\n"
            "- source: where the data came from (e.g., article title, tweet ID, image file name, etc.)\n"
            "- reason: Why this is included (e.g., reported jam, accident, heavy rain, etc.)\n\n"
            "Only use information present in the input data. Do not fabricate or assume anything. Keep the report strictly factual and clean."
        ),
        data_text=json.dumps({
            "last_24h_data": last_24h_data_sorted,
        }, indent=4)
    )

    guide_output = send_to_vertex(guide_prompt)
    # print(guide_prompt)
    # print("Guide Output:", guide_output.content.decode('utf-8'))
    # print("making alerts ready")
    global top_alerts
    # Parse the guide output for alerts (assuming JSON format)
    try:
        # Fetch last 24h data from Firestore where agent_name == "messenger"
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)
        messenger_data = [
            item for item in fetch_data(start_time, end_time)
            if item.get('agent_name') == 'messenger'
        ]
        # print("Messenger Data:", messenger_data)
        # Extract alerts from messenger_data (assuming json_data contains alerts)
        alerts = []
        for item in messenger_data:
            try:
                data = item.get('json_data')
                if isinstance(data, str):
                    data = json.loads(data)
                # If data is a list of alerts, extend; else, append
                if isinstance(data, list):
                    alerts.extend(data)
                elif isinstance(data, dict) and 'alerts' in data:
                    alerts.extend(data['alerts'])
                else:
                    alerts.append(data)
            except Exception as e:
                print(f"Error parsing messenger alert: {e}")
        # Take top 10 alerts
        top_alerts = alerts[:10]
    except Exception as e:
        print(f"Failed to load messenger alerts: {e}")
        top_alerts = []
    # print("Top Alerts:", top_alerts)

    # --- Load twitter data and prepare dashboard table ---
    twitter_data = twitter_data_fetch()
    # If twitter_data is a dict, convert to list of rows for table
    if isinstance(twitter_data, dict):
        twitter_table = []
        for key, value in twitter_data.items():
            row = {'key': key, 'value': value}
            twitter_table.append(row)
    elif isinstance(twitter_data, list):
        twitter_table = twitter_data
    else:
        twitter_table = []

    dashboard_dictionary = {
        "twitter_table": twitter_table
    }
    # print("Dashboard Dictionary:", dashboard_dictionary)
    # Extract all "text" fields from the 'data' value in twitter_table
    global output_alerts
    output_alerts = []
    for row in dashboard_dictionary["twitter_table"]:
        if row.get("key") == "data" and isinstance(row.get("value"), list):
            for item in row["value"]:
                if isinstance(item, dict) and "text" in item:
                    output_alerts.append(item["text"])
    # print("Output Alerts:", output_alerts)
    insert_data("messenger", twitter_data_fetch())

    global hindi_alerts, kannada_alerts
    hindi_alerts = []
    for alert in output_alerts:
        translated = translate_text(alert, "hi")
        hindi_alerts.append(translated)
    # print("Hindi Alerts:", hindi_alerts)

    kannada_alerts = []
    for alert in output_alerts:
        translated = translate_text(alert, "kn")
        kannada_alerts.append(translated)
    # print("Kannada Alerts:", kannada_alerts)


#----------------------------------------------------------

# Create your views here.
def home_page(request):
    master_agent(request)
    # translated = translate_text("Hello, how are you?", "es")  # Translates to Spanish
    # print("Translated text:", translated)
    return render(request, 'home.html')

def listener(request):
    return render(request, 'listener.html')

def judge(request):
    return render(request, 'judge.html')

def scanner(request):
    return render(request, 'scanner.html')

def artist(request):
    return render(request, 'artist.html')  

def telescope(request):
    return render(request, 'telescope.html')

def guide(request):
    return render(request, 'guide.html', {"output_alerts": output_alerts})

def messenger(request):
    return render(request, 'messenger.html', {"hindi_alerts": hindi_alerts, "kannada_alerts": kannada_alerts})




# All your existing views here...
# ...

def mood_data(request):
    # Fetch last 24 hours of data where agent_name is 'messenger'
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    messenger_data = [
        item for item in fetch_data(start_time, end_time)
        if item.get('agent_name') == 'messenger'
    ]
    # print("Messenger Data:", messenger_data[:30])

    # Extract latitude, longitude, and severity from messenger_data
    data = []
    for item in messenger_data:
        # Try to extract json_data
        json_data = item.get('json_data')
        if isinstance(json_data, str):
            try:
                json_data = json.loads(json_data)
            except Exception:
                continue
        # If json_data is a dict with 'data' key (from twitter_table)
        if isinstance(json_data, dict) and 'data' in json_data:
            records = json_data['data']
        # If json_data is a list of records
        elif isinstance(json_data, list):
            records = json_data
        else:
            records = []

        for record in records:
            lat = record.get('latitude')
            lon = record.get('longitude')
            severity = record.get('severity', '').lower()
            # Map severity to mood
            if severity in ['critical', 'high']:
                mood = 'sad'
            elif severity in ['medium']:
                mood = 'calm'
            elif severity in ['low']:
                mood = 'happy'
            else:
                mood = 'calm'
            if lat is not None and lon is not None:
                data.append({
                    "latitude": lat,
                    "longitude": lon,
                    "mood": mood
                })
    # print("filtered-------------------------------------------------------------",data)
    # If no data found, fallback to static mock data
    if not data:
        data = [
            {"latitude": 12.9716, "longitude": 77.5946, "mood": "happy"},
            {"latitude": 12.9352, "longitude": 77.6142, "mood": "sad"},
            {"latitude": 13.0358, "longitude": 77.5970, "mood": "angry"},
            {"latitude": 12.9876, "longitude": 77.6789, "mood": "calm"},
        ]
    return JsonResponse(data, safe=False)
# _____________ db connection______________________

# from .firebase_config import db

def fetch_and_store_weather(request):
    # Example: OpenWeatherMap API
    api_key = 'YOUR_API_KEY'
    city = 'Bengaluru'
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}'

    response = requests.get(url)
    data = response.json()

    # Store in Firestore
    doc_ref = db.collection('weather_reports').document(city)
    doc_ref.set(data)

    return JsonResponse({'status': 'stored', 'city': city})
# ____________________________________________________________________________