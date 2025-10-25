import requests
from bs4 import BeautifulSoup
import json
import hashlib
from datetime import datetime
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
INPUT_FILE = 'bakeplaysmile_links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'bakeplaysmile.com'
DELIVERY_VERSION = 'V1.0'
MAX_WORKERS = 10

def parse_recipe_card(recipe_container):
    """
    Parses only the specified parts of a wprm-recipe-container:
    Title, Ingredients, Instructions, and Notes.
    """
    if not recipe_container:
        return ""
        
    parts = []
    
    # Recipe Title
    title_tag = recipe_container.select_one('h2.wprm-recipe-name')
    if title_tag:
        parts.append(title_tag.get_text(strip=True).upper())

    # Ingredients
    ingredients_container = recipe_container.select_one('.wprm-recipe-ingredients-container')
    if ingredients_container:
        parts.append("\nIngredients")
        for ing in ingredients_container.select('.wprm-recipe-ingredient'):
            parts.append(ing.get_text(separator=' ', strip=True).replace('▢ ', ''))

    # Instructions
    instructions_container = recipe_container.select_one('.wprm-recipe-instructions-container')
    if instructions_container:
        parts.append("\nInstructions")
        for group in instructions_container.select('.wprm-recipe-instruction-group'):
            group_title = group.select_one('.wprm-recipe-instruction-group-name')
            if group_title:
                parts.append(f"\n{group_title.get_text(strip=True)}")
            for instruction in group.select('.wprm-recipe-instruction'):
                parts.append(instruction.get_text(strip=True))

    # Notes
    notes_container = recipe_container.select_one('.wprm-recipe-notes-container')
    if notes_container:
        notes_text = notes_container.get_text(strip=True)
        # The header is included in get_text, so we check if there's more than just "Notes"
        if len(notes_text) > 6:
            parts.append(f"\n{notes_text}")
            
    return '\n'.join(parts)


def scrape_article(url: str) -> dict | None:
    """
    Scrapes a single recipe article from bakeplaysmile.com.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        page_title = soup.select_one('h1.entry-title').get_text(strip=True)
        content_area = soup.select_one('div.entry-content')

        if not content_area:
            return None

        # --- 1. Aggressive Cleanup: Remove all specified unwanted elements ---
        selectors_to_remove = [
            '.adthrive', '.wprm-recipe-snippet', '.dpsp-pin-it-button',
            'details#feast-advanced-jump-to', '.is-style-group-quote',
            '.feast-ai-buttons-block', '.feast-category-index',
            '.dpsp-post-pinterest-image-hidden', 'span#dpsp-post-content-markup'
        ]
        for selector in selectors_to_remove:
            for element in content_area.select(selector):
                element.decompose()

        # Remove specific sections by their header ID
        ids_to_remove = [
            '#white-chocolate-cheesecake-faqs', 
            '#more-no-bake-cheesecake-recipes',
            '#need-to-substitute-an-ingredient'
        ]
        for element_id in ids_to_remove:
            header = content_area.select_one(element_id)
            if header:
                parent_group = header.find_parent('div', class_='wp-block-group')
                if parent_group:
                    parent_group.decompose()
                else:
                    header.decompose()

        # --- MODIFIED PART ---
        # Remove paragraphs that are just cross-promotional links or social links (case-insensitive)
        for p in content_area.find_all('p'):
            text = p.get_text().lower() # Convert text to lowercase
            if "you might also enjoy my" in text or \
               "don't miss my" in text or \
               "want even more delicious recipes?" in text: # Check against lowercase strings
                p.decompose()

        # --- 2. Process Content ---
        content_parts = []
        
        for element in content_area.select('h2, p, ul, ol, .wp-block-image, .wprm-recipe-container'):
            if element.find_parent(class_='wprm-recipe-container'):
                continue
                
            if element.name in ['h2', 'p']:
                content_parts.append(element.get_text(strip=True))
            elif element.name in ['ul', 'ol']:
                for li in element.find_all('li'):
                    content_parts.append(f"- {li.get_text(strip=True)}")
            elif 'wp-block-image' in element.get('class', []):
                img = element.find('img')
                if img and (img.get('src') or img.get('data-lazy-src')):
                    img_url = img.get('data-lazy-src') or img.get('src')
                    content_parts.append(f"[image: {img_url}]")
        
        main_recipe_card = content_area.select_one('.wprm-recipe-container')
        if main_recipe_card:
            content_parts.append("\n" + parse_recipe_card(main_recipe_card))

        # --- 3. Assemble and Finalize ---
        full_content_text = '\n'.join(filter(None, content_parts))
        full_content_text = re.sub(r'\n{3,}', '\n\n', full_content_text).strip()

        if len(full_content_text) < 200:
            return None

        processing_date = datetime.now().strftime("%Y-%m-%d")
        
        data = {
            "ID": hashlib.md5(url.encode('utf-8')).hexdigest(),
            "Text": f"{page_title}\n{full_content_text}",
            "meta": {
                "data_info": {
                    "lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Article",
                    "processing_date": processing_date, "delivery_version": DELIVERY_VERSION,
                    "title": page_title, "content": full_content_text,
                    "content_info": {
                        "domain": "daily_life",
                        "subdomain": "Cooking Tips, food knowledge, food preservation"
                    }
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