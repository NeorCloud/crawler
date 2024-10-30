import hashlib
import os
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

# Nginx cache settings
cache_dir = "/root/nginx/cache"
temp_cache_dir = "/tmp/cache"
cache_path_levels = "1:2"

def generate_cache_key(url):
    # Generate a cache key using this pattern: $scheme$request_method$host$request_uri
    parsed_url = urlparse(url)
    cache_key = f"{parsed_url.scheme}GET{parsed_url.hostname}{parsed_url.path}"
    return cache_key

def get_cache_file_path(cache_key):
    # Generate a cache path using nginx's cache directory and the md5 hash of the cache key
    cache_key_md5 = hashlib.md5(cache_key.encode()).hexdigest()

    if cache_path_levels == "1:2":
        return os.path.join(cache_dir, cache_key_md5[-1], cache_key_md5[-3:-1], cache_key_md5)
    elif cache_path_levels == "1:2:3":
        return os.path.join(cache_dir, cache_key_md5[-1], cache_key_md5[-3:-1], cache_key_md5[-6:-3], cache_key_md5)
    else:
        return os.path.join(cache_dir, cache_key_md5)

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

async def renew_page_cache(session, url):
    # Get the cache key from the URL
    cache_key = generate_cache_key(url)

    logging.info(f"Checking availibility of {url}")
    cache_file_path = get_cache_file_path(cache_key)
    logging.debug(f"Cache file path: {cache_file_path}")
    try:
        if os.path.exists(cache_file_path):
            logging.debug(f"Cache file found for {cache_file_path}")
            # Move the cache file to the temp directory
            temp_cache_file_path = os.path.join(temp_cache_dir, cache_file_path)
            os.makedirs(os.path.dirname(temp_cache_file_path), exist_ok=True)
            os.rename(cache_file_path, temp_cache_file_path)
            # Try to fetch the URL
            content_type, response = await fetch_page(session, url)
            if not response:
                logging.error(f"Failed to fetch {url}")
                # Move the cache file back to the cache directory
                os.rename(temp_cache_file_path, cache_file_path)
                logging.warning(f"Cache file restored for {cache_key}")
                return False
            # Remove the cache file from the temp directory
            os.remove(temp_cache_file_path)
            logging.info(f"Succesfully renewed cache for {url}")
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to renew cache for {url}: {e}")
        return False


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
            renew_cache = await renew_page_cache(session, url)
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