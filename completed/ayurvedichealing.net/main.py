import requests
from bs4 import BeautifulSoup
import json
import hashlib
from datetime import datetime
import re

# --- Configuration ---
INPUT_FILE = 'links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'ayurvedichealing.net' # Used for the 'source' field
DELIVERY_VERSION = 'V1.0'

def scrape_article(url: str) -> dict | None:
    """
    Scrapes a single article URL and returns the data in the required format.
    Returns None if scraping fails.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        soup = BeautifulSoup(response.content, 'html.parser')

        # --- 1. Extract Title ---
        title_tag = soup.find('h1', class_='entry-title')
        if not title_tag:
            print(f"Warning: Title not found for {url}")
            return None
        title = title_tag.get_text(strip=True)

        # --- 2. Extract Main Image ---
        # The image is usually the first one in the article content.
        image_tag = soup.find('img', {'data-stretch': 'false'})
        image_url = image_tag.get('data-src') if image_tag else ""
        image_markdown = f"[image: {image_url}]" if image_url else ""

        # --- 3. Extract Article Content ---
        content_div = soup.find('div', class_='sqs-html-content')
        if not content_div:
            print(f"Warning: Content not found for {url}")
            return None
        
        # Get all text elements (p, li, h1-h6) and join them
        content_elements = content_div.find_all(['p', 'li', 'h2', 'h3', 'h4'])
        content_parts = [elem.get_text(strip=True) for elem in content_elements]
        
        # Filter out empty strings that might result from empty tags
        content_parts = [part for part in content_parts if part]

        # Join with a single newline
        full_content_text = '\n'.join(content_parts)

        # --- 4. Final Formatting Checks ---
        # Ensure there are no multiple consecutive newlines
        full_content_text = re.sub(r'\n{2,}', '\n', full_content_text).strip()
        
        # Check for minimum length
        if len(full_content_text) < 200:
            print(f"Warning: Content for {url} is too short ({len(full_content_text)} chars). Skipping.")
            return None

        # --- 5. Assemble the JSON object ---
        processing_date = datetime.now().strftime("%Y-%m-%d")
        
        # Prepend image to content
        content_with_image = f"{image_markdown}{full_content_text}" if image_markdown else full_content_text
        
        data = {
            "ID": hashlib.md5(url.encode('utf-8')).hexdigest(),
            "Text": f"{title}\n{content_with_image}",
            "meta": {
                "data_info": {
                    "lang": "en",
                    "url": url,
                    "source": WEBSITE_NAME,
                    "type": "Article",
                    "processing_date": processing_date,
                    "delivery_version": DELIVERY_VERSION,
                    "title": title,
                    "content": content_with_image,
                    "content_info": {
                        "domain": "daily_life",
                        "subdomain": "Health tips and personal care"
                    }
                }
            }
        }
        return data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred while processing {url}: {e}")
        return None


def main():
    """
    Main function to read URLs, scrape them, and save the results.
    """
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f_in:
            urls = [line.strip() for line in f_in if line.strip()]
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        return

    print(f"Found {len(urls)} URLs to process.")
    
    scraped_count = 0
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
        for i, url in enumerate(urls):
            print(f"Processing ({i+1}/{len(urls)}): {url}")
            article_data = scrape_article(url)
            if article_data:
                # Convert dict to JSON string and write to file, followed by a newline
                f_out.write(json.dumps(article_data, ensure_ascii=False) + '\n')
                scraped_count += 1

    print(f"\nScraping complete. Successfully processed and saved {scraped_count} articles to '{OUTPUT_FILE}'.")

if __name__ == '__main__':
    main()