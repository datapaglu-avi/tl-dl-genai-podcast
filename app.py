# Step 1 - Read config.yml to detch list of channel and their id

from typing import TypedDict, List, Dict
import yaml # type: ignore
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from youtube_transcript_api import YouTubeTranscriptApi, _errors
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import asyncio
import edge_tts

# Constants & Type Classes

ytt_api = YouTubeTranscriptApi()
load_dotenv()

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
    transcript: str

BASE_URL_RSS_FEED_XML = 'https://www.youtube.com/feeds/videos.xml?channel_id='
NOW_UTC = datetime.now(timezone.utc)
OUTPUT_FILE = "podcast.mp3"

# Methods
# Step 1 = Read config file for list of channels
def read_config_yml(file_path: str) -> Dict[str, List[Channel]]:

    # with open(file_path, 'r') as f:
    #     config = yaml.safe_load(f)
    
    # return config

    try:
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return config
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
            print(f'XML Fetched for channel - {channel["name"]}')
            return response.content

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as err:
        print(f"Request error occurred: {err}")
    except Exception as e:
        print(f"An unexpected error occurred at step 2: {e}")

# Step 3 - Parse XML byte string and get the desired fields: video id, thumbnail, published date (if within 24hrs)
def parse_xml_byte_string(xml_byte_str: bytes, c: Channel) -> Video:
    ns = {
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'media': 'http://search.yahoo.com/mrss/',
        'atom': 'http://www.w3.org/2005/Atom'
      }
    
    rootElem = ET.fromstring(xml_byte_str)

    videos: List[Video] = []

    for entry in rootElem.findall('atom:entry', ns):
        published_ts_iso = entry.find('atom:published', ns).text
        published_ts_utc = datetime.fromisoformat(published_ts_iso)

        if (NOW_UTC - published_ts_utc <= timedelta(hours = 24)): 

            # Future TO:DO -> need to add condition to exclude upcoming videos
            video_id = entry.find('yt:videoId', ns).text
            video_title = entry.find('atom:title', ns).text
            video_thumbnail_url = entry.find('.//media:thumbnail', ns).attrib['url']

            channel_title_constraint = c['video_title_regex']

            if channel_title_constraint != 'N/A':
                if channel_title_constraint in video_title:
                    videos.append (
                        Video (
                            id = video_id,
                            title = video_title,
                            thumbnail_url = video_thumbnail_url,
                            channel_id = c['id']
                        )
                    )
            else:
                videos.append (
                        Video (
                            id = video_id,
                            title = video_title,
                            thumbnail_url = video_thumbnail_url,
                            channel_id = c['id']
                        )
                    )
        else:
            # Old video - do not process its entry
            continue

    return videos

# Step 4 - Get video transcript
def get_transcript_for_a_video(v: Video, c: Channel) -> str:
    print(f'Processing video - {v["title"]} for channel {c["name"]}')

    try:
        v_id = v['id']
        default_lang = c['language']
        fetched_transcript = ytt_api.fetch(v_id, languages = [default_lang, 'en'])

        transcript = ''

        if len(fetched_transcript) > 0:
            for t in fetched_transcript:
                transcript += (' ' + t.text)
        else:
            print(f'No transcript found for video id {v_id}')

        return transcript
    except _errors.VideoUnavailable as vu:
        print(f'Video unavailable - video id: {v_id}\n{vu}')

# Step 5 - Use OpenAI + Langchain to get the video transcript summarised.
def ask_llm_to_summarise(script: str) -> str:
    llm = ChatOpenAI(model = 'gpt-4.1-nano')

    messages = [
        SystemMessage('''You are a transcript summariser. Summarise this video in clear, concise bullet points. Capture the key news stories and insights shared by the host, including their interpretations or opinions. Avoid using any greetings, disclaimers, or brand promotions. Keep the tone neutral and podcast-friendly. Do not reference visuals or ask the listener to 'watch' anything. Output in a clear, engaging tone as if spoken by a narrator. Incase the input is hindi, then also output should be in English. Keep the crux of the content, i.e. minimal info loss - remove the fluff'''),
        HumanMessage(script)
    ]

    response = llm.invoke(messages)
    summary = response.content

    return summary

# Step 6 - Use OpenAI + LangChain to convert the summary into 2 people podcast
def ask_llm_to_gen_podcast_script(script: str) -> str:
    llm = ChatOpenAI(model = 'gpt-4.1-nano')

    messages = [
        SystemMessage('''
        Convert the following news summary into a solo podcast script. Keep it smooth, human-like, and avoid robotic narration. Break longer pieces into smaller, natural-sounding segments. Language for the output script should be in English.

        Tone: Conversational, casual, and informed — like a host casually updating listeners on the news.

        Format:

        Start with this opening line:

        “Good morning, it’s [today’s date]. Here’s your Business News wrap.”

        Then, immediately follow with this disclaimer:

        “Quick heads-up — this is an AI-generated summary based on multiple sources. Please verify key info independently. Also, none of this is financial advice or a buy/sell recommendation.”

        After the disclaimer, proceed with the news content in a clear, listener-friendly flow.
                                    
        '''),
        HumanMessage(script)
    ]

    response = llm.invoke(messages)
    transcript = response.content

    return transcript

# Step 7 - Get Audio
async def text_to_speech(speech: str):
    communicate = edge_tts.Communicate(speech, voice = "en-IN-PrabhatNeural", rate = "+50%")  # You can change the voice
    await communicate.save(OUTPUT_FILE)


if __name__ == '__main__':
    # 1. read the config file
    print('Step #1 start')
    channel_dict = read_config_yml('./config.yml')

    summaries = []

    for channel in channel_dict['channels']:
        # 2. Fetch the xml for channel
        xml_bytes = fetch_xml_for_a_channel(channel = channel)

        # 3. Parse the xml to get videos to process
        videos = parse_xml_byte_string(xml_bytes, channel)

        for video in videos:
            # 4. Get transcript
            print('Step #4 start')
            try:
                transcript = get_transcript_for_a_video(video, channel)
            except Exception as e:
                try:
                    transcript = get_transcript_for_a_video(video, channel)
                except Exception as e2:
                    print(f'Getting error {e2} when trying to fetch transcript for video: {video["name"]}')

            # 5. Summary of the transcript
            print('Step #5 start')
            summary = ask_llm_to_summarise(transcript)
            summaries.append(summary)

    # 6. Convert all summary to a single podcast
    print('Step #6 start')
    podcast_transcript = ask_llm_to_gen_podcast_script('\n'.join(summaries))

    # 7. Audio file
    print('Step #7 start')
    with open('temp_file.txt', 'w') as f:
        print(podcast_transcript, file = f)
    asyncio.run(text_to_speech(podcast_transcript))