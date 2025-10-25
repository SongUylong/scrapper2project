import time
import re
import json
import hashlib
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag

# --- Configuration ---
INPUT_FILE = 'all_article_links.txt' # Make sure this file contains URLs from afrovitalityeats.com
OUTPUT_FILE = 'output.jsonl'
WEBSITE_NAME = 'afrovitalityeats.com'
DELIVERY_VERSION = 'V1.0'
MAX_WORKERS = 4

# --- Text Cleaning Functions ---

def normalize_text(text: str) -> str:
    """Handles basic text normalization for punctuation, emojis, and whitespace structuring."""
    if not isinstance(text, str): return ""

    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('…', '...').replace('–', '-').replace('—', '-')

    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F" # emoticons
        "\U0001F300-\U0001F5FF" # symbols & pictographs
        "\U0001F680-\U0001F6FF" # transport & map symbols
        "\U0001F1E0-\U0001F1FF" # flags (iOS)
        "\U0001F900-\U0001F9FF" # Supplemental Symbols and Pictographs
        "\U0001FA70-\U0001FAFF" # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0" # Dingbats
        "\U000024C2-\U0001F251"
        "\U0000FE00-\U0000FE0F" # Variation Selectors
        "\U000020D0-\U000020FF"
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub(r'', text)

    # Correct whitespace handling: collapse multiple spaces, collapse multiple newlines
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)

    return text.strip()

def anonymize_text(text: str) -> str:
    """Anonymizes PII like emails and phone numbers, skipping image tags."""
    if not isinstance(text, str): return ""

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

def get_cleaned_text(element: Tag) -> str:
    """Gets text from a BS4 element and cleans internal newlines and excess whitespace."""
    if not element:
        return ""
    # Use .stripped_strings to handle potential multiple lines/tags within an element better
    text_parts = list(element.stripped_strings)
    text = ' '.join(text_parts)
    # Replace remaining multiple spaces just in case
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_wprm_recipe_card(recipe_container: Tag) -> str:
    """Parses a WPRM (WP Recipe Maker) recipe card, removing unwanted elements."""
    if not recipe_container:
        return ""

    # (Code for parsing WPRM card - unchanged from previous version)
    selectors_to_remove_from_card = [
        '.wprm-template-chic-buttons','.wprm-recipe-buttons','.wprm-recipe-print',
        '.wprm-recipe-pin','.wprm-recipe-jump','.wprm-recipe-adjustable-servings-container',
        '.wprm-recipe-shop-instacart','.wprm-icon-shortcode','h3.wprm-recipe-nutrition-header',
        '.wprm-nutrition-label-container','.wprm-recipe-keyword-container',
        '.wprm-call-to-action','.wprm-recipe-user-rating','.wprm-entry-info','.wprm-entry-footer',
    ]
    for selector in selectors_to_remove_from_card:
        for element in recipe_container.select(selector):
            element.decompose()
    parts = []
    title_tag = recipe_container.select_one('h2.wprm-recipe-name')
    if title_tag: parts.append(get_cleaned_text(title_tag).upper())
    summary_tag = recipe_container.select_one('.wprm-recipe-summary')
    if summary_tag: parts.append(get_cleaned_text(summary_tag))
    prep_time_tag = recipe_container.select_one('.wprm-recipe-prep-time-container .wprm-recipe-time')
    cook_time_tag = recipe_container.select_one('.wprm-recipe-cook-time-container .wprm-recipe-time')
    if prep_time_tag or cook_time_tag:
        time_parts = []
        if prep_time_tag: time_parts.append(f"Prep Time: {get_cleaned_text(prep_time_tag)}")
        if cook_time_tag: time_parts.append(f"Cook Time: {get_cleaned_text(cook_time_tag)}")
        parts.append("\n" + ", ".join(time_parts))
    ingredients_container = recipe_container.select_one('.wprm-recipe-ingredients-container')
    if ingredients_container:
        ingredients_header = ingredients_container.select_one('h3.wprm-recipe-ingredients-header')
        if ingredients_header: parts.append(f"\n{get_cleaned_text(ingredients_header)}")
        for group in ingredients_container.select('.wprm-recipe-ingredient-group'):
            group_header = group.select_one('h4.wprm-recipe-group-name')
            if group_header: parts.append(f"\n{get_cleaned_text(group_header)}")
            for li in group.select('li.wprm-recipe-ingredient'):
                amount = get_cleaned_text(li.select_one('.wprm-recipe-ingredient-amount'))
                unit = get_cleaned_text(li.select_one('.wprm-recipe-ingredient-unit'))
                name = get_cleaned_text(li.select_one('.wprm-recipe-ingredient-name'))
                notes = get_cleaned_text(li.select_one('.wprm-recipe-ingredient-notes'))
                ingredient_line = f"- {amount} {unit} {name}".strip()
                if notes: ingredient_line += f" ({notes})"
                parts.append(ingredient_line.replace('▢', '').strip())
    instructions_container = recipe_container.select_one('.wprm-recipe-instructions-container')
    if instructions_container:
        instructions_header = instructions_container.select_one('h3.wprm-recipe-instructions-header')
        if instructions_header: parts.append(f"\n{get_cleaned_text(instructions_header)}")
        for group in instructions_container.select('.wprm-recipe-instruction-group'):
            group_header = group.select_one('h4.wprm-recipe-group-name')
            if group_header: parts.append(f"\n{get_cleaned_text(group_header)}")
            instruction_list = group.select_one('ul.wprm-recipe-instructions, ol.wprm-recipe-instructions')
            if instruction_list:
                for i, li in enumerate(instruction_list.find_all('li', recursive=False), 1):
                    instruction_text = get_cleaned_text(li)
                    if instruction_text: parts.append(f"{i}. {instruction_text}")
    notes_container = recipe_container.select_one('.wprm-recipe-notes-container')
    if notes_container:
        notes_header = notes_container.select_one('h3.wprm-recipe-notes-header')
        notes_content_element = notes_container.select_one('.wprm-recipe-notes')
        if notes_content_element:
             notes_text = get_cleaned_text(notes_content_element)
             if notes_text:
                parts.append(f"\n{get_cleaned_text(notes_header) if notes_header else 'Notes'}")
                parts.append(notes_text)
    return '\n'.join(filter(None, parts))


def parse_html_content(html: str, url: str) -> dict | None:
    """Parses the full HTML content using BeautifulSoup."""
    soup = BeautifulSoup(html, 'html.parser')

    # 1. Find the main article container
    article_container = soup.select_one('article.entry')
    if not article_container:
        print(f"No 'article.entry' found for {url}")
        return None

    # 2. Get the title
    title_tag = article_container.select_one('h1.entry-title')
    if not title_tag:
        print(f"No 'h1.entry-title' found for {url}")
        return None
    title = get_cleaned_text(title_tag)

    # 3. Determine subdomain
    subdomain = "Cooking" # Default
    category_link = article_container.select_one('p.entry-meta .entry-categories a[href*="/backyard-garden/"]')
    # Use get_cleaned_text for robustness
    if category_link and "Backyard Garden" in get_cleaned_text(category_link):
        subdomain = "Planting"

    # 4. Get the main content area
    content_area = article_container.select_one('.entry-content')
    if not content_area:
        print(f"No '.entry-content' found for {url}")
        return None

    # 5. --- Decompose common and type-specific junk ---
    selectors_to_remove = [
        '.entry-meta', '.share-before', '.share-after', '.google-auto-placed',
        '.ap_container', 'ins.adsbygoogle', '.jp-relatedposts', '.wprm-recipe-snippet',
    ]
    for selector in selectors_to_remove:
        for element in article_container.select(selector):
            element.decompose()

    # 6. --- Handle Recipe Card (if Cooking) ---
    recipe_text = ""
    if subdomain == "Cooking":
        # Look for the recipe container *within the potentially modified content_area*
        recipe_card_container = content_area.select_one('div[id*="wprm-recipe-container-"]')
        if recipe_card_container:
            recipe_text = parse_wprm_recipe_card(recipe_card_container)
            recipe_card_container.decompose() # Remove after parsing


    # 7. --- Extract the main article text ---
    content_parts = []
    # Iterate through direct children of content_area
    for element in content_area.children:
        if not isinstance(element, Tag):
            continue

        # Skip known containers we don't want to iterate inside further
        if element.name == 'div' and ('wprm-recipe-container' in element.get('id','')):
             continue # Already processed recipe card

        # --- MODIFIED BLOCK FOR TEXT TAGS (p, h2, h3, h4) ---
        if element.name in ['p', 'h2', 'h3', 'h4']:
            # First, check for an image *within* this element
            img = element.find('img')
            if img:
                img_url = img.get('data-lazy-src') or img.get('data-src') or img.get('src')
                width = img.get('width')
                height = img.get('height')
                try:
                    if img_url and img_url.startswith('http') and (not width or int(width) > 30) and (not height or int(height) > 30) and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")
                except (ValueError, TypeError):
                    if img_url and img_url.startswith('http') and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")

            # Then, get the text content of the element itself
            text = get_cleaned_text(element)
            # Only append text if it's not empty (handles cases where <p> only contains <img>)
            if text:
                content_parts.append(text)
        # --- END MODIFIED BLOCK ---

        # Handle lists (Unchanged)
        elif element.name in ['ul', 'ol']:
            for li in element.find_all('li', recursive=False):
                li_text = get_cleaned_text(li)
                if li_text:
                    content_parts.append(f"- {li_text}")

        # Handle figures (single images and galleries - Unchanged)
        elif element.name == 'figure' and ('wp-block-image' in element.get('class', []) or 'wp-block-gallery' in element.get('class', [])):
            images = element.find_all('img')
            for img in images:
                img_url = img.get('data-lazy-src') or img.get('data-src') or img.get('src')
                width = img.get('width')
                height = img.get('height')
                try:
                    if img_url and img_url.startswith('http') and (not width or int(width) > 30) and (not height or int(height) > 30) and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")
                except (ValueError, TypeError):
                     if img_url and img_url.startswith('http') and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")
            caption = element.find('figcaption')
            if caption:
                caption_text = get_cleaned_text(caption)
                if caption_text:
                    content_parts.append(f"Caption: {caption_text}")

        # Add more specific tag handling if needed


    # 8. --- Combine, Clean, and Format ---
    article_text = '\n'.join(filter(None, content_parts))
    full_content_text = f"{article_text}\n\n{recipe_text}".strip()

    normalized_title = normalize_text(title)
    cleaned_content = anonymize_text(normalize_text(full_content_text))

    text_for_length_check = re.sub(r'\[image: [^\]]+\]', '', cleaned_content)
    min_length = 100 if recipe_text else 150
    if len(text_for_length_check) < min_length:
        print(f"Skipped {url}: Content too short ({len(text_for_length_check)} chars, needed {min_length}) after cleaning.")
        return None

    processing_date = datetime.now().strftime("%Y-%m-%d")

    domain_info = {
        "domain": "daily_life",
        "subdomain": "Planting" if subdomain == "Planting" else "Cooking Tips, food knowledge, food preservation"
    }

    data = {
        "ID": hashlib.md5(url.encode('utf-8')).hexdigest(),
        "Text": f"{normalized_title}\n{cleaned_content}",
        "meta": {
            "data_info": {
                "lang": "en", "url": url, "source": WEBSITE_NAME, "type": "Blog",
                "processing_date": processing_date, "delivery_version": DELIVERY_VERSION,
                "title": normalized_title, "content": cleaned_content,
                "content_info": domain_info
            }
        }
    }
    return data

def scrape_url_task(url: str):
    """Fetches and parses a single URL using Playwright and BeautifulSoup."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Allow images, block others
            page.route("**/*", lambda route: route.abort() if route.request.resource_type in {"stylesheet", "font", "media"} else route.continue_())
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            # Give page a moment longer to potentially finish rendering images
            page.wait_for_timeout(1000) # Wait 1 second
            html = page.content()
            return parse_html_content(html, url)
        except Exception as e:
            print(f"Playwright/Navigation Error for {url}: {e}")
            return None
        finally:
            page.close()
            browser.close()

def main():
    """Main function to read URLs, manage scraping processes, and write output."""
    scraped_urls = set()
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f_out:
            for line in f_out:
                try:
                    data = json.loads(line)
                    scraped_urls.add(data['meta']['data_info']['url'])
                except (json.JSONDecodeError, KeyError, TypeError):
                    print(f"Skipping malformed line in output file: {line.strip()}")
                    continue
        print(f"Found {len(scraped_urls)} already scraped URLs. Resuming...")
    except FileNotFoundError:
        print("Output file not found. Starting a new scrape.")

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f_in:
            all_urls = {line.strip() for line in f_in if line.strip() and line.strip().startswith('http')}
            urls_to_scrape = sorted(list(all_urls - scraped_urls))
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found. Please create it.")
        return

    if not urls_to_scrape:
        print("All URLs from the input file have already been scraped or the file is empty. Nothing to do.")
        return

    print(f"Total unique URLs in input file: {len(all_urls)}. Already scraped: {len(scraped_urls)}. Remaining to scrape: {len(urls_to_scrape)}.")
    start_time = time.time()
    scraped_count = 0
    skipped_count = 0
    error_count = 0

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(scrape_url_task, url): url for url in urls_to_scrape}

            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    article_data = future.result()
                    if article_data:
                        try:
                           json_string = json.dumps(article_data, ensure_ascii=False)
                           f_out.write(json_string + '\n')
                           scraped_count += 1
                           print(f"✅ SUCCESS: Scraped {url}")
                        except TypeError as json_err:
                            print(f"❌ JSON SERIALIZATION ERROR for {url}: {json_err}. Data: {article_data}")
                            error_count += 1
                    else:
                         print(f"⏭️ SKIPPED/NO DATA: {url}")
                         skipped_count +=1
                except Exception as exc:
                    print(f"❌ UNEXPECTED ERROR during processing for {url}: {exc}")
                    error_count += 1

    end_time = time.time()
    total_time = end_time - start_time
    print("\n--- Scraping Complete ---")
    print(f"Successfully scraped and saved: {scraped_count}")
    print(f"Skipped (no data/too short): {skipped_count}")
    print(f"Errors during processing: {error_count}")
    print(f"Total URLs attempted this run: {len(urls_to_scrape)}")
    print(f"Total time taken: {total_time:.2f} seconds.")

if __name__ == '__main__':
    main()