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
                continue
        else:
            # Old video - do not process its entry
            continue

    return videos

# Step 4 - Get video transcript
def get_transcript_for_a_video(v: Video, c: Channel) -> str:
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


async def text_to_speech(speech: str):
    communicate = edge_tts.Communicate(speech, voice = "en-IN-PrabhatNeural", rate = "+50%")  # You can change the voice
    await communicate.save(OUTPUT_FILE)



# for testing - only on "Yadnya Investment Academy"
for channel in channel_config['channels']:
    if channel['name'] != 'Yadnya Investment Academy':
        continue

    xml_byte_str = fetch_xml_for_a_channel(channel = channel)

    videos = parse_xml_byte_string(xml_byte_str, channel)
    # if len > 0
    script = get_transcript_for_a_video(videos[0], channel)

    # summary = ask_llm_to_summarise(script)

    summary = '''
    - Global markets experienced mixed reactions; US and European markets were initially positive but lost some enthusiasm after key decisions on tariffs and trade tensions.
    - US court ruling declared Donald Trump’s reciprocal tariffs as revoked and invalid, easing market fears temporarily.
    - Markets anticipate that Trump may pursue legal challenges against the ruling, with upcoming Supreme Court hearings expected.
    - US Federal Reserve Chair Jerome Powell meeting with Trump indicated no immediate interest rate cuts, despite speculation; market expects possible rate reductions after upcoming Fed meetings.
    - US 10-year Treasury yields declined slightly, reflecting expectations of interest rate cuts and potential economic slowdown, with jobless claims increasing.
    - Crude oil prices remain around $64.5, favorable for India’s import costs; gold continues fluctuating based on geopolitical news, staying near all-time highs within a $100 range.
    - US macroeconomic data shows a modest growth in corporate earnings; NVI stocks and overall NASDAQ performed well, supported by crypto-friendly policies under the Trump administration.
    - Bitcoin and cryptocurrencies are benefiting from government efforts to influence currency and asset prices; crypto prices remain volatile amid regulatory developments.
    - Global market sentiments are cautious but positive overall; European markets initially responded positively but adjusted after realizing potential market adjustments.
    - India-US trade negotiations are ongoing, with key dates in June; discussions include mutual trade targets and resolving internal US court disputes affecting trade agreements.
    - Construction equipment sales increased marginally by 3% in FY25, significantly lower than previous years’ growth; slowdown attributed to election-related restrictions and delayed project execution.
    - RBI annual report highlighted stress on gold loan portfolios due to rising gold prices and stricter LTV (Loan to Value) norms; companies may face losses if they fail to monitor LTV ratios.
    - Microfinance and consumer finance sectors continue to undergo regulatory scrutiny; RBI emphasizes proactive measures before issues escalate.
    - Digital Rupee (CBDC) development is progressing, with active transaction volume and cross-border use cases; RBI focusing more on private sector digital currency initiatives, contrasting US approach of private crypto company-led developments.
    - Companies like Cadence reported a 11% revenue increase with margin improvements; gold jewelry companies showed strong growth supported by gold price increases.
    - Electric vehicle maker Ola Electric reported poor quarterly results, with revenue down nearly 60%, driven by one-time factors and supply chain issues; optimistic about future margins and volume growth with new models.
    - Bajaj Auto’s exports grew by 20%, with EV segment making significant contributions; supply chain disruptions in rare-earth metals from China pose risks for EV component sourcing.
    - Adani Ports issued nearly 5000 crore bonds, picked up by LIC at 7.75% coupon, with plans to sell assets to Reliance, Apollo, and possibly Aramco; strategic portfolio adjustments underway.
    - Impact of AI tools like ChatGPT reducing the time and manpower needed for IPO prospectuses and other financial documents; 95% of work now automated, emphasizing the need for upskilling.
    - AI evolution is leading to automation across consulting, law, accounting, architecture, and other high-skilled jobs; encouraging ongoing reskilling without fear of job loss.
    - Major firms like Microsoft and Google are planning layoffs or restructuring due to AI-led automation, reinforcing importance of adaptability.
    - The message advocates continuous skill development to remain relevant and leverage AI as a tool for productivity rather than fear of obsolescence.
    - Overall, focus on embracing technological change, balancing risks with opportunities, and staying proactive in skill enhancement for future job security.
    '''

    # podcast = ask_llm_to_gen_podcast_script(script=summary)
    
    podcast = '''
    Good morning, it’s May 30th. Here’s your Business News wrap.

    Quick heads-up — this is an AI-generated summary based on multiple sources. Please verify key info independently. Also, none of this is financial advice or a buy/sell recommendation.

    First up, let’s talk markets. Globally, we saw mixed reactions today. The US and European markets started off on a positive note, but momentum eased a bit after some key decisions on tariffs and trade tensions. 

    In a significant development, a US court ruled that Donald Trump’s reciprocal tariffs are revoked and declared them invalid. That temporarily eased some market fears, but everyone’s watching to see if Trump might challenge this ruling legally, with upcoming Supreme Court hearings on the horizon.

    Meanwhile, at the Federal Reserve, Chair Jerome Powell met with Trump — but there was no immediate hint at interest rate cuts, despite all the speculation. Markets are now eyeing future Fed meetings—many expect some rate reductions after those.

    Bond markets reflected this sentiment too. The US 10-year Treasury yields declined slightly, which suggests investors are thinking about potential rate cuts and maybe a slowing economy. On the economic front, jobless claims rose a bit, adding to concerns about growth.

    On commodities, crude oil stays around $64.50, which is good news for countries like India that import oil, keeping costs manageable. Gold prices continue to fluctuate based on geopolitical news, lingering near all-time highs within a $100 range.

    Looking at US economic data, corporate earnings showed modest growth, and stocks like those in the NASDAQ performed well. Interestingly, the tech sector benefited from policies friendly to cryptocurrencies, which have been getting some government support in recent times. Bitcoin and other cryptos are quite volatile right now, influenced by regulatory developments and government efforts to sway currency and asset markets.

    Global market sentiment remains cautious but overall positive. European markets, for instance, initially responded well but then dialed back a bit, realizing that some adjustments might be ahead.

    On the international trade front, India and the US are deep into negotiations, with key dates set for June. These talks cover mutual trade targets and resolving some internal US court disputes that are influencing trade agreements.

    Switching gears to the economy back home — construction equipment sales saw a modest 3% rise in FY25, but that’s lower than previous years. The slowdown is mainly due to election-related restrictions and delays in project execution.

    The RBI’s latest annual report highlighted some stress in gold loan portfolios, driven by rising gold prices and stricter loan-to-value norms. Companies might face losses if they don’t vigilantly monitor their LTV ratios. Additionally, the microfinance and consumer finance sectors continue to face regulatory scrutiny, with the RBI emphasizing proactive measures.

    On digital currency, the Reserve Bank is making progress with the Digital Rupee (CBDC). Active transaction volumes and cross-border use cases are already in play. Interestingly, the RBI seems more focused on encouraging private sector digital currency initiatives, contrasting with the US where private crypto companies are leading the charge.

    Now, onto some company updates. Cadence, a tech firm, reported an 11% jump in revenue with better margins. Gold jewelry companies are also performing well, buoyed by rising gold prices.

    However, not all news is positive. Ola Electric reported a tough quarter, with revenues down nearly 60%. The drop was due to one-time factors and supply chain issues, but the company remains optimistic about future margins and volume growth with new models.

    Bajaj Auto’s exports grew by 20%, especially in the EV segment, which is a bright spot. But there’s a looming risk: disruptions in rare-earth metal supplies from China could impact EV component sourcing.

    On the infrastructure front, Adani Ports issued nearly 5,000 crore worth of bonds, bought by LIC at a 7.75% coupon. The group plans to sell assets to Reliance, Apollo, and possibly Aramco as part of strategic portfolio adjustments.

    And here’s an interesting one — AI tools like ChatGPT are transforming financial document work. Today, about 95% of IPO prospectuses and similar tasks are automated, reducing time and manpower. This shift emphasizes the importance of upskilling for professionals across consulting, law, accounting, and architecture. 

    Major firms like Microsoft and Google are planning layoffs or restructuring, citing AI-led automation. But this is also a chance for individuals to stay proactive—by continuously reskilling and adapting.

    The key takeaway? Embrace technological change, balance risks and opportunities, and keep developing your skills. AI isn’t just a threat; it’s a powerful tool to boost productivity — if we’re ready to use it smartly.

    That’s your latest update for today. Thanks for tuning in, and I’ll catch you next time!
    '''


    asyncio.run(text_to_speech(podcast))
