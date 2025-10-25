import requests
from bs4 import BeautifulSoup
import json
import hashlib
from datetime import datetime
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
INPUT_FILE = 'bakingbar_links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'bakingbar.co.uk'
DELIVERY_VERSION = 'V1.0'
MAX_WORKERS = 10

# --- NEW: Function for all text cleaning and anonymization ---
def clean_text(text: str) -> str:
    """
    Applies a series of cleaning and anonymization rules to the text.
    """
    if not isinstance(text, str):
        return ""

    # 1. Anonymize PII
    # Anonymize emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    text = re.sub(email_pattern, lambda m: 'x' * len(m.group()), text)
    # Anonymize phone numbers (basic formats)
    phone_pattern = r'(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}'
    text = re.sub(phone_pattern, lambda m: 'x' * len(m.group()), text)

    # 2. Normalize punctuation and special characters
    text = text.replace('’', "'").replace('‘', "'")
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('…', '...').replace('–', '-').replace('—', '-')

    # 3. Filter emojis and other special symbols
    emoji_pattern = re.compile(
        "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    
    # 4. Normalize whitespace and line breaks
    # Replace multiple spaces with a single space
    text = re.sub(r' +', ' ', text)
    # Ensure no more than one consecutive line break
    text = re.sub(r'\n{2,}', '\n', text)
    # Remove leading/trailing whitespace from the whole text block
    text = text.strip()

    return text


def determine_subdomain(title: str) -> str:
    """
    Determines the appropriate subdomain based on keywords in the article title.
    """
    title_lower = title.lower()
    
    if 'interview' in title_lower or 'q&a' in title_lower:
        return "Food Culture & People"
        
    return "Cooking Tips, food knowledge, food preservation"

def scrape_article(url: str) -> dict | None:
    """
    Scrapes a single article URL from bakingbar.co.uk.
    """
    try:
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        title_tag = soup.select_one('h1.cm-entry-title')
        if not title_tag: return None
        title = title_tag.get_text(strip=True)

        subdomain = determine_subdomain(title)

        content_area = soup.select_one('div.cm-entry-summary')
        if not content_area: return None
            
        for ad_block in content_area.select('.quads-location'):
            ad_block.decompose()

        content_parts = []

        featured_image_tag = soup.select_one('.cm-featured-image img')
        if featured_image_tag and featured_image_tag.get('src'):
            content_parts.append(f"[image: {featured_image_tag['src']}]")

        for element in content_area.find_all(['p', 'div', 'figure'], recursive=True):
            if element.name == 'div' and 'block-title' in element.get('class', []):
                heading = element.find('h4')
                if heading:
                    content_parts.append(f"\n{heading.get_text(strip=True)}")
            elif element.name == 'p':
                if not element.find_parent(class_='block-title'):
                    text = element.get_text(strip=True)
                    if text: content_parts.append(text)
            elif element.name == 'figure' and 'wp-block-image' in element.get('class', []):
                img = element.find('img')
                if img and img.get('src'):
                    content_parts.append(f"[image: {img['src']}]")

        full_content_text = '\n'.join(filter(None, content_parts))
        
        # --- APPLY CLEANING AND ANONYMIZATION ---
        cleaned_title = clean_text(title)
        cleaned_content = clean_text(full_content_text)
        
        if len(cleaned_content) < 200: return None

        processing_date = datetime.now().strftime("%Y-%m-%d")
        
        data = {
            "ID": hashlib.md5(url.encode('utf-8')).hexdigest(),
            "Text": f"{cleaned_title}\n{cleaned_content}",
            "meta": {
                "data_info": {
                    "lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Article",
                    "processing_date": processing_date, "delivery_version": DELIVERY_VERSION,
                    "title": cleaned_title, "content": cleaned_content,
                    "content_info": { "domain": "daily_life", "subdomain": subdomain }
                }
            }
        }
        return data
    except Exception as e:
        raise IOError(f"Failed to process {url}") from e

def main():
    """Reads URLs and uses a thread pool to scrape them concurrently."""
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found. Please create it.")
        return

    print(f"Found {len(urls)} URLs. Starting scrape with {MAX_WORKERS} workers...")
    start_time = time.time()
    scraped_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(scrape_article, url): url for url in urls}
        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    article_data = future.result()
                    if article_data:
                        f_out.write(json.dumps(article_data, ensure_ascii=False) + '\n')
                        scraped_count += 1
                        print(f"✅ SUCCESS: Scraped {url}")
                    else:
                        print(f"⏭️ SKIPPED: {url} (No data returned or content too short)")
                except Exception as exc:
                    print(f"❌ ERROR: {url} generated an exception: {exc}")

    end_time = time.time()
    total_time = end_time - start_time
    print("\n--- Scraping Complete ---")
    print(f"Successfully processed and saved {scraped_count} out of {len(urls)} articles.")
    print(f"Total time taken: {total_time:.2f} seconds.")

if __name__ == '__main__':
    main()