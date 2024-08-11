import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(description="Crawl a website")
parser.add_argument("url", help="The URL of the website to crawl")
parser.add_argument("--domains", nargs="+", help="List of allowed domains")

visited_urls = set()

allowed_domains = set()

def fetch_page(url):
    try:
        # Change schema to http
        url = re.sub(r'^https', 'http', url)
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None

def extract_links_from_html(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
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

def crawl(start_url):
    queue = [start_url]
    while queue:
        url = queue.pop()
        if url in visited_urls:
            continue
        text = fetch_page(url)
        if text:
            visited_urls.add(url)
            time.sleep(0.5)
            if url.endswith('.js') or url.endswith('.css'):
                links = extract_links_from_text(text, url)
            else:
                links = extract_links_from_html(text, url)
            queue += links


if __name__ == "__main__":
    args = parser.parse_args()
    start_url = args.url
    if args.domains:
        allowed_domains.update(args.domains)
    logging.info(f"Start crawling at {start_url}")
    crawl(start_url)
    logging.info(f"Crawling complete with {len(visited_urls)} visited URLs")