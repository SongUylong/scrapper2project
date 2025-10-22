import time
import re
import json
import hashlib
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- Configuration ---
INPUT_FILE = 'all_articles_links.txt'
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'africanbites.com'
DELIVERY_VERSION = 'V1.0'
MAX_WORKERS = 4
DEBUG_SAVE_HTML = False

# --- Text Cleaning Functions ---

def normalize_text(text: str) -> str:
    """Handles basic text normalization for punctuation, emojis, and whitespace."""
    if not isinstance(text, str): return ""
    
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('…', '...').replace('–', '-').replace('—', '-')

    # --- EMOJI FILTER UPDATED ---
    # Expanded pattern to include newer Unicode emoji blocks
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

    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    
    return text.strip()

def anonymize_text(text: str) -> str:
    """Anonymizes PII like emails and phone numbers."""
    if not isinstance(text, str): return ""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    text = re.sub(email_pattern, lambda m: 'x' * len(m.group()), text)
    phone_pattern = r'(\(?\d{3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}'
    text = re.sub(phone_pattern, lambda m: 'x' * len(m.group()), text)
    return text

def parse_wprm_recipe_card(recipe_container):
    """Parses only the specified parts of a WPRM recipe container."""
    if not recipe_container:
        return ""
    for unwanted in recipe_container.select('.wprm-social, .socialShare, .wprm-recipe-user-rating, .wprm-entry-info, .wprm-entry-footer, .wprm-entry-nutrition, .wprm-recipe-print, .wprm-call-to-action, .wprm-unit-conversion-container'):
        unwanted.decompose()

    parts = []
    title_tag = recipe_container.select_one('h2.wprm-recipe-name')
    if title_tag:
        parts.append(title_tag.get_text(strip=True).upper())

    ingredients_container = recipe_container.select_one('.wprm-recipe-ingredients-container')
    if ingredients_container:
        parts.append("\nIngredients")
        for group in ingredients_container.select('.wprm-recipe-ingredient-group'):
            group_title = group.select_one('.wprm-recipe-ingredient-group-name')
            if group_title:
                parts.append(f"\n{group_title.get_text(strip=True)}")
            for item in group.select('.wprm-recipe-ingredient'):
                ingredient_text = ' '.join(item.stripped_strings).replace('▢', '').strip()
                if ingredient_text:
                    parts.append(ingredient_text)

    instructions_container = recipe_container.select_one('.wprm-recipe-instructions-container')
    if instructions_container:
        parts.append("\nInstructions")
        for group in instructions_container.select('.wprm-recipe-instruction-group'):
            group_title = group.select_one('.wprm-recipe-instruction-group-name')
            if group_title:
                parts.append(f"\n{group_title.get_text(strip=True)}")
            for i, instruction in enumerate(group.select('.wprm-recipe-instruction'), 1):
                instruction_text = instruction.get_text(strip=True)
                if instruction_text:
                    parts.append(f"{i}. {instruction_text}")

    notes_container = recipe_container.select_one('.wprm-recipe-notes-container')
    if notes_container:
        notes_list = [li.get_text(strip=True) for li in notes_container.select('ol > li, ul > li')]
        if notes_list:
            parts.append("\nNotes:")
            parts.extend(notes_list)

    return '\n'.join(parts)


def parse_html_content(html: str, url: str) -> dict | None:
    """Parses the full HTML content using BeautifulSoup."""
    soup = BeautifulSoup(html, 'html.parser')
    
    article_container = soup.select_one('article.single-entry')
    if not article_container:
        return None

    selectors_to_remove = [
        '#kadence-breadcrumbs', 
        '.entry-meta', 
        'div#dpsp-content-top', 
        '.wprm-recipe-snippet',
        '#savetherecipe', 
        '.mv-ad-box', 
        'h2#more-recipes', 
        'h2#more-recipes + ol, h2#more-recipes + p + ul',
        '.navigation.post-navigation', 
        '.entry-related', 
        '#comments', 
        '.wprm-nutrition-label-shortcode-container',
        '.lwptoc_i'
    ]
    for selector in selectors_to_remove:
        for element in article_container.select(selector):
            element.decompose()

    content_parts = []
    title_tag = article_container.select_one('h1.entry-title')
    if not title_tag: return None
    title = title_tag.get_text(strip=True)

    content_area = article_container.select_one('.entry-content')
    if not content_area: return None

    selector_string = 'p, h2, h3, ol, ul, figure.wp-block-image, div[id*="wprm-recipe-container-"]'
    
    for element in content_area.select(selector_string, recursive=True):
        if not hasattr(element, 'get'):
            continue

        is_in_recipe_card = element.find_parent(class_='wprm-recipe-container')
        is_recipe_card_itself = 'wprm-recipe-container' in element.get('id', '')
        
        if is_in_recipe_card and not is_recipe_card_itself:
            continue

        if is_recipe_card_itself:
            content_parts.append("\n" + parse_wprm_recipe_card(element))
        elif element.name in ['p', 'h2', 'h3']:
            text = element.get_text(strip=True)
            if text: content_parts.append(text)
        elif element.name in ['ol', 'ul']:
            for li in element.find_all('li', recursive=False):
                content_parts.append(f"- {li.get_text(strip=True)}")
        elif element.name == 'figure':
            img = element.find('img')
            if img:
                img_url = img.get('data-src') or img.get('src')
                if img_url:
                    content_parts.append(f"[image: {img_url}]")

    full_content_text = '\n'.join(filter(None, content_parts))
    normalized_title = normalize_text(title)
    cleaned_content = anonymize_text(normalize_text(full_content_text))
    
    if len(cleaned_content) < 200: return None
    
    processing_date = datetime.now().strftime("%Y-%m-%d")
    data = {"ID": hashlib.md5(url.encode('utf-8')).hexdigest(), "Text": f"{normalized_title}\n{cleaned_content}", "meta": {"data_info": {"lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Blog", "processing_date": processing_date, "delivery_version": DELIVERY_VERSION, "title": normalized_title, "content": cleaned_content, "content_info": {"domain": "daily_life", "subdomain": "Cooking Tips, food knowledge, food preservation"}}}}
    return data

def scrape_url_task(url: str):
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
            if DEBUG_SAVE_HTML:
                filename = re.sub(r'[\\/*?:"<>|]', "", url.replace("https://", "").replace("http://", "").replace("/", "_")) + ".html"
                with open(filename, 'w', encoding='utf-8') as f: f.write(html)
                print(f"🐛 DEBUG: Saved raw HTML for {url} to '{filename}'")
            return parse_html_content(html, url)
        finally:
            page.close()
            browser.close()

def main():
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
            all_urls = {line.strip() for line in f_in if line.strip()}
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