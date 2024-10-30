import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import argparse
import logging

# Set up logging
logging.basicConfig(format='%(process)d:%(levelname)s:%(module)s:%(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="Crawl a website")
parser.add_argument("url", help="The URL of the website to crawl")
parser.add_argument("--domains", nargs="+", help="List of allowed domains")
parser.add_argument("--purge", action="store_true", help="Purge each URL cache before visiting", default=False)
parser.add_argument("--clean-cache", action="store_true", help="Clean the cache after crawling", default=False)

visited_urls = set()
allowed_domains = set()
semaphore = asyncio.Semaphore(20)

async def fetch_page(session, url):
    try:
        # Change schema to http
        url = re.sub(r'^https', 'http', url)
        logging.info(f"Fetching {url}")
        async with semaphore:
            async with session.get(url) as response:
                response.raise_for_status()
                _ = await response.read()
                return (response.headers.get('Content-Type'), response)
    except aiohttp.ClientError as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return (None, None)
    except asyncio.TimeoutError as e:
        logging.error(f"Timeout error for {url}: {e}")
        return (None, None)
    
async def purge_page(session, url):
    try:
        # Change schema to http
        url = re.sub(r'^https', 'http', url)
        logging.info(f"Purging {url}")
        async with semaphore:
            async with session.request('PURGE', url) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientError as e:
        # Check if the URL is already purged and response code is 404
        if e.status == 404:
            logging.info(f"URL {url} is already purged")
            return None
        logging.error(f"Failed to purge {url}: {e}")
        return None

def extract_links_from_html(html, base_url):
    try:
        soup = BeautifulSoup(html, 'html.parser')
    except Exception as e:
        logging.error(f"Failed to parse {base_url}: {e}")
        return set()
    links = set()
    
    # Extract links from <a> tags
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)
    
    # Extract links from <link> tags (CSS files)
    for link_tag in soup.find_all('link', href=True):
        href = link_tag['href']
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)
    
    # Extract links from <script> tags (JS files)
    for script_tag in soup.find_all('script', src=True):
        src = script_tag['src']
        full_url = urljoin(base_url, src)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)
    
    # Extract links from <img> tags (images)
    for img_tag in soup.find_all('img', src=True):
        src = img_tag['src']
        full_url = urljoin(base_url, src)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)
    
    # Extract links from <video> tags (video files)
    for video_tag in soup.find_all('video', src=True):
        src = video_tag['src']
        full_url = urljoin(base_url, src)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)
    
    # Extract links from <audio> tags (audio files)
    for audio_tag in soup.find_all('audio', src=True):
        src = audio_tag['src']
        full_url = urljoin(base_url, src)
        if urlparse(full_url).netloc in allowed_domains:
            links.add(full_url)

    logging.info(f"Found {len(links)} links on {base_url}")
    return links

def extract_links_from_text(text, base_url):
    links = set()
    regex = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    matches = re.findall(regex, text)
    for match in matches:
        full_url = urljoin(base_url, match)
        if urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)
    logging.info(f"Found {len(links)} links on {base_url}")
    return links

async def crawl(session, start_url):
    queue = {start_url}
    while queue:
        logging.info(f"{start_url} - Queue: {len(queue)}, Visited: {len(visited_urls)}")
        url = queue.pop()
        if url in visited_urls:
            logging.info(f"Already visited {url}")
            continue
        if args.purge:
            purge_response = await purge_page(session, url)
            logger.debug(f"Purge response: {purge_response}")
        content_type, response = await fetch_page(session, url)
        if args.clean_cache:
            purge_response = await purge_page(session, url)
            logger.debug(f"Purge response: {purge_response}")
        if response and response.ok:
            logging.info(f"Successfully fetched {url}: {response.status}, {content_type}")
            visited_urls.add(url)
        else:
            continue
        if content_type in ['text/html', 'text/css', 'application/javascript'] or content_type.startswith('text/'):
            text = await response.text()
            if url.endswith('.js') or url.endswith('.css'):
                links = extract_links_from_text(text, url)
            else:
                links = extract_links_from_html(text, url)
            queue.update(links)

async def main(start_url):
    async with aiohttp.ClientSession() as session:
        await crawl(session, start_url)

if __name__ == "__main__":
    args = parser.parse_args()
    start_url = args.url
    if args.domains:
        allowed_domains.update(args.domains)
    logging.info(f"Start crawling at {start_url}")
    logging.info(f"Allowed domains: {allowed_domains}")
    asyncio.run(main(start_url))
    logging.info(f"Crawling complete with {len(visited_urls)} visited URLs")