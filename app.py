# Step 1 - Read config.yml to detch list of channel and their id

from typing import TypedDict, List, Dict
import yaml # type: ignore
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


# Constants & Type Classes

class Channel(TypedDict):
    name: str
    id: str
    video_title_regex: str
    language: str

class Video(TypedDict):
    title: str
    id: str
    thumbnail_url: str
    channel_id: str

BASE_URL_RSS_FEED_XML = 'https://www.youtube.com/feeds/videos.xml?channel_id='
NOW_UTC = datetime.now(timezone.utc)

# Methods

def read_config_yml(file_path: str) -> Dict[str, List[Channel]]:

    with open(file_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config

try:
    channel_config = read_config_yml('./config.yml')
except FileNotFoundError as e:
    print(f"File not found: {e}")
except Exception as e:
    print(f"An unexpected error occurred at step 1: {e}")


# Step 2 - Fetch the XML from internet
def fetch_xml_for_a_channel(channel: Channel) -> bytes:
    try:
        # chnl_name = channel['name']
        chnl_id = channel['id']
        # chnl_video_title_regex = channel['video_title_regex']
        # chnl_language = channel['language']

        url = BASE_URL_RSS_FEED_XML + chnl_id

        response = requests.get(url)
        response.raise_for_status()  # Raise error if request failed

        if response.status_code == 200:
            return response.content

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as err:
        print(f"Request error occurred: {err}")
    except Exception as e:
        print(f"An unexpected error occurred at step 2: {e}")

# Step 3 - Parse XML byte string and get the desired fields: video id, thumbnail, published date (if within 24hrs)

def parse_xml_byte_string(xml_byte_str: bytes, channel_id: str) -> Video:
    ns = {
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'media': 'http://search.yahoo.com/mrss/',
        'atom': 'http://www.w3.org/2005/Atom'
      }
    
    rootElem = ET.fromstring(xml_byte_str)

    for entry in rootElem.findall('atom:entry', ns):
        published_ts_iso = entry.find('atom:published', ns).text
        published_ts_utc = datetime.fromisoformat(published_ts_iso)

        if NOW_UTC - published_ts_utc <= timedelta(hours = 24):
            video_id = entry.find('yt:videoId', ns).text
            video_title = entry.find('atom:title', ns).text
            video_thumbnail_url = entry.find('.//media:thumbnail', ns).attrib['url']

            return Video(
                id = video_id,
                title = video_title,
                thumbnail_url = video_thumbnail_url,
                channel_id = channel_id
            )
        
        else:
            # Old video - do not process its entry
            continue

    print(rootElem.tag)

# for testing - only on "Yadnya Investment Academy"
for channel in channel_config['channels']:
    if channel['name'] != 'Yadnya Investment Academy':
        continue

    xml_byte_str = fetch_xml_for_a_channel(channel=channel)

    video = parse_xml_byte_string(xml_byte_str, 'fnfjn')

    print(video)

    

