import time
import re
import json
import hashlib
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag

# --- Configuration ---
INPUT_FILE = 'pure_links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'aglugofoil.com'
DELIVERY_VERSION = 'V1.0'
MAX_WORKERS = 4

# --- Text Cleaning Functions ---

def normalize_text(text: str) -> str:
    """Handles basic text normalization for punctuation, emojis, and WHITESPACE STRUCTURING."""
    if not isinstance(text, str): return ""
    
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('…', '...').replace('–', '-').replace('—', '-')

    # --- EMOJI FILTER (Unchanged) ---
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs (NEW)
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A (NEW - Catches 🫵)
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251" 
        "\U0000FE00-\U0000FE0F"  # Variation Selectors
        "\U000020D0-\U000020FF"
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub(r'', text)

    # --- WHITESPACE HANDLING (REVERTED) ---
    # This now correctly preserves our single \n separators and just cleans up multiples.
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    
    return text.strip()

def anonymize_text(text: str) -> str:
    """Anonymizes PII like emails and phone numbers, skipping image tags."""
    if not isinstance(text, str): return ""

    # (Unchanged)
    image_tag_pattern = r'(\[image: [^\]]+\])'
    image_tags = re.findall(image_tag_pattern, text)
    placeholder = '___IMG_TAG_PLACEHOLDER___'
    text_with_placeholders = re.sub(image_tag_pattern, placeholder, text)
    
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    anonymized_text = re.sub(email_pattern, lambda m: 'x' * len(m.group()), text_with_placeholders)
    
    phone_pattern = r'(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}'
    anonymized_text = re.sub(phone_pattern, lambda m: 'x' * len(m.group()), anonymized_text)
    
    tag_iter = iter(image_tags)
    final_text = re.sub(placeholder, lambda m: next(tag_iter), anonymized_text)
    
    return final_text

# --- NEW HELPER FUNCTION ---
def get_cleaned_text(element: Tag) -> str:
    """
    Gets text from a BS4 element and cleans all internal newlines and excess whitespace.
    This fixes the problem of single \n chars inside a <p> tag.
    """
    if not element:
        return ""
    text = element.get_text()
    # Replace all whitespace (newlines, tabs, multiple spaces) with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
# --- END NEW HELPER ---


def parse_ccm_recipe_card(recipe_container: Tag) -> str:
    """
    Parses the specific 'ccm-card' recipe box from aglugofoil.com.
    (MODIFIED: Now uses get_cleaned_text)
    """
    if not recipe_container:
        return ""

    # 1. Clean up junk (Unchanged)
    selectors_to_remove_from_card = [
        '.ccm-pinit-btn', '.ccm-hide-on-print', '.ccm-btns-wrapper', 'iframe',
        '.mv-ad-box', '.ccm-cook-mode', '.ccm-posturl', '.ccm-copyright',
        '.ccm-instagram-credit', '.ccm-credit'
    ]
    for selector in selectors_to_remove_from_card:
        for element in recipe_container.select(selector):
            element.decompose()

    parts = []

    # 2. Extract recipe data (MODIFIED: uses get_cleaned_text)
    title_tag = recipe_container.select_one('h3.ccm-name')
    if title_tag:
        parts.append(get_cleaned_text(title_tag).upper()) # <-- UPDATED

    summary_tag = recipe_container.select_one('.ccm-summary p')
    if summary_tag:
        parts.append(get_cleaned_text(summary_tag)) # <-- UPDATED

    times_container = recipe_container.select_one('.ccm-time')
    if times_container:
        times = [get_cleaned_text(t) for t in times_container.select('.ccm-time-child')] # <-- UPDATED
        parts.append(f"\nTime: {', '.join(times)}")

    ingredients_container = recipe_container.select_one('.ccm-section-ingredients')
    if ingredients_container:
        ing_title = ingredients_container.select_one('h3.ccm-head')
        if ing_title:
            parts.append(f"\n{get_cleaned_text(ing_title)}") # <-- UPDATED
        for li in ingredients_container.select('ul.ccm-section-items li'):
            parts.append(f"- {get_cleaned_text(li)}") # <-- UPDATED

    instructions_container = recipe_container.select_one('.ccm-section-instructions')
    if instructions_container:
        inst_title = instructions_container.select_one('h3.ccm-head')
        if inst_title:
            parts.append(f"\n{get_cleaned_text(inst_title)}") # <-- UPDATED
        
        pre_step = instructions_container.select_one('.ccm-section-title')
        if pre_step:
            parts.append(get_cleaned_text(pre_step)) # <-- UPDATED
            
        for i, li in enumerate(instructions_container.select('ol.ccm-section-items li'), 1):
            parts.append(f"{i}. {get_cleaned_text(li)}") # <-- UPDATED

    return '\n'.join(parts)


def parse_html_content(html: str, url: str) -> dict | None:
    """
    Parses the full HTML content using BeautifulSoup.
    (MODIFIED: Now uses get_cleaned_text)
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Find container (Unchanged)
    article_container = soup.select_one('div.post.hentry')
    if not article_container:
        return None

    # 2. Get title (MODIFIED: uses get_cleaned_text)
    title_tag = article_container.select_one('h1.post-title.entry-title')
    if not title_tag: 
        return None
    title = get_cleaned_text(title_tag) # <-- UPDATED

    # 3. Get content area (Unchanged)
    content_area = article_container.select_one('.post-body.entry-content')
    if not content_area: 
        return None

    # 4. Handle Recipe Card (Unchanged)
    recipe_card = content_area.select_one('.ccm-card, #ccm-recipe-card')
    recipe_text = ""
    if recipe_card:
        recipe_text = parse_ccm_recipe_card(recipe_card)
        recipe_card.decompose() 

    # 5. Decompose junk (Unchanged)
    selectors_to_remove = [
        '.post-labels', '.post-meta', 'div[style*="margin-bottom: 14px"]', 'i',
        'div[data-testid*="inline-subscribe-cta"]', '.inline-subscribe',
        '.mv-ad-box', 'p.has-text-align-center', '#grow-me-in-content-recs-root',
        'script', 'style', '.addthis_toolbox', '.post-footer', 'iframe',
    ]
    for selector in selectors_to_remove:
        for element in article_container.select(selector):
            element.decompose()

    # 6. Extract main text (MODIFIED: uses get_cleaned_text)
    content_parts = []
    for element in content_area.children:
        if not isinstance(element, Tag):
            continue

        if element.name in ['p', 'h3']:
            text = get_cleaned_text(element) # <-- UPDATED
            if text and "You might also like my recipe for" not in text:
                content_parts.append(text)
        
        elif element.name == 'h2':
            img = element.find('img')
            if img:
                img_url = img.get('data-src') or img.get('src')
                if img_url:
                    content_parts.append(f"[image: {img_url}]")
            text = get_cleaned_text(element) # <-- UPDATED
            if text:
                content_parts.append(f"\n{text}\n")
        
        elif element.name in ['ol', 'ul']:
            for li in element.find_all('li', recursive=False):
                li_text = get_cleaned_text(li) # <-- UPDATED
                if li_text:
                    content_parts.append(f"- {li_text}")
        
        elif element.name == 'div' and 'separator' in element.get('class', []):
            img = element.find('img')
            if img:
                img_url = img.get('data-src') or img.get('src')
                if img_url:
                    content_parts.append(f"[image: {img_url}]")

    # 7. Combine, Clean, and Format (Unchanged)
    article_text = '\n'.join(filter(None, content_parts))
    full_content_text = f"{article_text}\n\n{recipe_text}" 
    
    normalized_title = normalize_text(title)
    cleaned_content = anonymize_text(normalize_text(full_content_text))
    
    text_for_length_check = re.sub(r'\[image: [^\]]+\]', '', cleaned_content)
    
    if len(text_for_length_check) < 200: 
        return None
    
    processing_date = datetime.now().strftime("%Y-%m-%d")
    data = {"ID": hashlib.md5(url.encode('utf-8')).hexdigest(), "Text": f"{normalized_title}\n{cleaned_content}", "meta": {"data_info": {"lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Blog", "processing_date": processing_date, "delivery_version": DELIVERY_VERSION, "title": normalized_title, "content": cleaned_content, "content_info": {"domain": "daily_life", "subdomain": "Cooking Tips, food knowledge, food preservation"}}}}
    return data

def scrape_url_task(url: str):
    # (Unchanged)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.route("**/*", lambda route: route.abort() if route.request.resource_type in {"stylesheet", "font", "media"} else route.continue_())
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.5)
            html = page.content()
            return parse_html_content(html, url)
        finally:
            page.close()
            browser.close()

def main():
    # (Unchanged)
    scraped_urls = set()
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f_out:
            for line in f_out:
                try:
                    data = json.loads(line)
                    scraped_urls.add(data['meta']['data_info']['url'])
                except (json.JSONDecodeError, KeyError): continue
        print(f"Found {len(scraped_urls)} already scraped URLs. Resuming...")
    except FileNotFoundError:
        print("Output file not found. Starting a new scrape.")
    
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f_in:
            all_urls = {line.strip() for line in f_in if line.strip()} #placed in a set to deduplicate
            urls_to_scrape = list(all_urls - scraped_urls)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found. Please create it.")
        return

    if not urls_to_scrape:
        print("All URLs from the input file have already been scraped. Nothing to do.")
        return

    print(f"Total URLs in file: {len(all_urls)}. Remaining to scrape: {len(urls_to_scrape)}.")
    start_time = time.time()
    scraped_count = 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(scrape_url_task, url): url for url in urls_to_scrape}
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
                        print(f"⏭️ SKIPPED: {url} (No data or content too short after cleaning)")
                except Exception as exc:
                    print(f"❌ ERROR: {url} generated an exception: {exc}")
    end_time = time.time()
    total_time = end_time - start_time
    print("\n--- Scraping Complete ---")
    print(f"Successfully processed and saved {scraped_count} new articles.")
    print(f"Total time taken: {total_time:.2f} seconds.")

if __name__ == '__main__':
    main()