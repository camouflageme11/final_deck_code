# utils.py

import requests

def detect_ai_image_with_hive(image_file, api_key):
    """
    Uploads an image file to Hive AI's API to detect if it is AI-generated.

    Args:
        image_file: Django UploadedFile object
        api_key: Your Hive API key as string

    Returns:
        dict: API response JSON with detection results
    """

    url = "https://api.thehive.ai/api/v2/moderation/predict/ai-image-detector"

    files = {
        'media': (image_file.name, image_file.read(), image_file.content_type)
    }

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.post(url, files=files, headers=headers)
    response.raise_for_status()  # raise error if request failed
    return response.json()
