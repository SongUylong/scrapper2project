import requests
from bs4 import BeautifulSoup
import json
import hashlib
from datetime import datetime
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
INPUT_FILE = 'bakefromscratch_links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'bakefromscratch.com'
DELIVERY_VERSION = 'V1.0'
# Set the number of concurrent threads to run
MAX_WORKERS = 10

def parse_recipe_block(recipe_element):
    """Helper function to parse a single recipe block."""
    recipe_parts = []
    
    recipe_title = recipe_element.select_one('h2.wprm-recipe-name')
    if recipe_title:
        recipe_parts.append(recipe_title.get_text(strip=True).upper())

    # Ingredients
    ingredients_container = recipe_element.select_one('div.wprm-recipe-ingredients-container')
    if ingredients_container:
        recipe_parts.append("\nIngredients")
        for ingredient in ingredients_container.select('li.wprm-recipe-ingredient'):
            parts = [span.get_text(strip=True) for span in ingredient.find_all('span')]
            recipe_parts.append(' '.join(parts))
    
    # Instructions
    instructions_container = recipe_element.select_one('div.wprm-recipe-instructions-container')
    if instructions_container:
        recipe_parts.append("\nInstructions")
        for i, instruction in enumerate(instructions_container.select('li.wprm-recipe-instruction'), 1):
            recipe_parts.append(f"{i}. {instruction.get_text(strip=True)}")

    # Notes
    notes_container = recipe_element.select_one('div.wprm-recipe-notes-container')
    if notes_container:
        notes_text_element = notes_container.select_one('div.wprm-recipe-notes')
        if notes_text_element:
            notes_text = notes_text_element.get_text(strip=True)
            if notes_text:
                recipe_parts.append("\nNotes")
                recipe_parts.append(notes_text)

    return '\n'.join(recipe_parts)

def scrape_article(url: str) -> dict | None:
    """
    Scrapes a single recipe article URL from bakefromscratch.com.
    This function is now executed by concurrent workers.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        title_tag = soup.select_one('h1.entry-title')
        if not title_tag:
            return None # Fail silently, main thread will report the skip
        title = title_tag.get_text(strip=True)

        content_area = soup.select_one('div.td-post-content')
        if not content_area:
            return None
            
        # Cleanup
        for unwanted in content_area.select('.adthrive, .adthrive-ad, .wprm-template-chic-buttons, .wprm-call-to-action, .wprm-recipe-summary'):
            unwanted.decompose()

        image_url = ""
        image_tag = content_area.select_one('div.td-post-featured-image img.entry-thumb')
        if image_tag and image_tag.get('src'):
            image_url = image_tag['src']

        # Process and Replace Recipe Blocks
        processed_recipes = {}
        recipe_blocks = content_area.select('div.wprm-recipe-container')
        for i, recipe_block in enumerate(recipe_blocks):
            placeholder = f"__RECIPE_PLACEHOLDER_{i}__"
            formatted_recipe_text = parse_recipe_block(recipe_block)
            processed_recipes[placeholder] = formatted_recipe_text
            recipe_block.replace_with(BeautifulSoup(placeholder, 'html.parser'))

        main_text = content_area.get_text(separator='\n', strip=True)

        for placeholder, recipe_content in processed_recipes.items():
            main_text = main_text.replace(placeholder, recipe_content)
        
        content_parts = []
        if image_url:
            content_parts.append(f"[image: {image_url}]")
        content_parts.append(main_text)
        full_content_text = '\n'.join(content_parts)
        full_content_text = re.sub(r'\n{3,}', '\n\n', full_content_text).strip()

        if len(full_content_text) < 200:
            return None

        processing_date = datetime.now().strftime("%Y-%m-%d")
        
        data = {
            "ID": hashlib.md5(url.encode('utf-8')).hexdigest(),
            "Text": f"{title}\n{full_content_text}",
            "meta": {
                "data_info": {
                    "lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Article",
                    "processing_date": processing_date, "delivery_version": DELIVERY_VERSION,
                    "title": title, "content": full_content_text,
                    "content_info": {
                        "domain": "daily_life",
                        "subdomain": "Cooking Tips, food knowledge, food preservation"
                    }
                }
            }
        }
        return data
    except Exception as e:
        # Raise exception to be caught by the main thread
        raise IOError(f"Failed to process {url}") from e

def main():
    """
    Reads URLs and uses a thread pool to scrape them concurrently.
    """
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found. Please create it.")
        return

    print(f"Found {len(urls)} URLs. Starting scrape with {MAX_WORKERS} workers...")
    start_time = time.time()
    scraped_count = 0

    # Using a ThreadPoolExecutor to manage concurrent workers
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all scrape_article tasks to the executor
        future_to_url = {executor.submit(scrape_article, url): url for url in urls}

        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
            # Process the results as they complete
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