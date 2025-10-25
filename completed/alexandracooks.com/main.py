import time
import re
import json
import hashlib
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag

# --- Configuration ---
INPUT_FILE = 'extracted_links.txt' # <<< Make sure this contains URLs for alexandracooks.com
OUTPUT_FILE = 'output_alexandra.jsonl' # <<< Changed output file name
WEBSITE_NAME = 'alexandracooks.com' # <<< Updated website name
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

def parse_tasty_recipes_card(recipe_container: Tag) -> str:
    """Parses a Tasty Recipes card, removing unwanted elements."""
    if not recipe_container:
        return ""

    # Remove buttons, ratings, footer, "other details" (stop point), ads inside
    selectors_to_remove_from_card = [
        '.tasty-recipes-buttons',
        '.tasty-recipes-rating',
        '.tasty-recipes-other-details', # Specific stop point
        '.tasty-recipes-entry-footer',
        '#AdThrive_Native_Recipe_1', # Ad inside ingredients
        '.tasty-recipes-ingredients-clipboard-container + .tasty-recipes-units-scale-container' # Scale buttons
    ]
    for selector in selectors_to_remove_from_card:
        for element in recipe_container.select(selector):
            element.decompose()

    parts = []

    # Extract Title
    title_tag = recipe_container.select_one('h2.tasty-recipes-title')
    if title_tag:
        parts.append(get_cleaned_text(title_tag).upper())

    # Extract Description (includes Notes section in this theme)
    description_section = recipe_container.select_one('.tasty-recipes-description')
    if description_section:
        desc_header = description_section.select_one('h3')
        if desc_header: parts.append(f"\n{get_cleaned_text(desc_header)}") # Add "Description" header
        desc_body = description_section.select_one('.tasty-recipes-description-body')
        if desc_body:
            # Iterate through p and li tags within description body
            for element in desc_body.find_all(['p', 'ul', 'h4'], recursive=False):
                 if element.name == 'ul':
                     for li in element.find_all('li'):
                         li_text = get_cleaned_text(li)
                         if li_text: parts.append(f"- {li_text}")
                 elif element.name == 'h4': # Handle notes header within description
                     h4_text = get_cleaned_text(element)
                     if h4_text: parts.append(f"\n{h4_text}")
                 else: # Handle p tags
                    p_text = get_cleaned_text(element)
                    if p_text: parts.append(p_text)


    # Extract Times and Yield from header details
    total_time_tag = recipe_container.select_one('.tasty-recipes-details li.total-time')
    prep_time_tag = recipe_container.select_one('.tasty-recipes-details li.prep-time') # Might not exist, but check
    cook_time_tag = recipe_container.select_one('.tasty-recipes-details li.cook-time') # Might not exist, but check
    yield_tag = recipe_container.select_one('.tasty-recipes-details li.yield')

    if total_time_tag or prep_time_tag or cook_time_tag:
        time_parts = []
        # Get text after the label span
        if prep_time_tag: time_parts.append(f"Prep Time: {get_cleaned_text(prep_time_tag.select_one('span:last-child'))}")
        if cook_time_tag: time_parts.append(f"Cook Time: {get_cleaned_text(cook_time_tag.select_one('span:last-child'))}")
        if total_time_tag: time_parts.append(f"Total Time: {get_cleaned_text(total_time_tag.select_one('span:last-child'))}")
        parts.append("\n" + ", ".join(time_parts))

    if yield_tag:
        yield_text = get_cleaned_text(yield_tag.select_one('span:last-child'))
        parts.append(f"Yield: {yield_text}")


    # Extract Ingredients
    ingredients_container = recipe_container.select_one('.tasty-recipes-ingredients')
    if ingredients_container:
        ingredients_header = ingredients_container.select_one('h3')
        if ingredients_header:
            parts.append(f"\n{get_cleaned_text(ingredients_header)}")
        # Iterate through ingredient groups (h4) and lists (ul)
        for element in ingredients_container.find_all(['h4', 'ul'], recursive=False):
            if element.name == 'h4':
                parts.append(f"\n{get_cleaned_text(element)}")
            elif element.name == 'ul':
                for li in element.find_all('li'):
                    # Tasty Recipes often doesn't use spans for amount/unit/name within li
                    li_text = get_cleaned_text(li)
                    if li_text: parts.append(f"- {li_text}")


    # Extract Instructions
    instructions_container = recipe_container.select_one('.tasty-recipes-instructions')
    if instructions_container:
        instructions_header = instructions_container.select_one('h3')
        if instructions_header:
            parts.append(f"\n{get_cleaned_text(instructions_header)}")
        # Iterate through instruction groups (h4) and lists (ol)
        for element in instructions_container.find_all(['h4', 'ol'], recursive=False):
            if element.name == 'h4':
                 parts.append(f"\n{get_cleaned_text(element)}")
            elif element.name == 'ol':
                for i, li in enumerate(element.find_all('li'), 1):
                    instruction_text = get_cleaned_text(li)
                    if instruction_text:
                        parts.append(f"{i}. {instruction_text}")

    return '\n'.join(filter(None, parts))


def parse_html_content(html: str, url: str) -> dict | None:
    """Parses the full HTML content using BeautifulSoup for alexandracooks.com."""
    soup = BeautifulSoup(html, 'html.parser')

    # 1. Find the main article container
    article_container = soup.select_one('article.post.single-post-content')
    if not article_container:
        print(f"No 'article.post.single-post-content' found for {url}")
        return None

    # 2. Get the title
    title_tag = article_container.select_one('h1.post-title')
    if not title_tag:
        print(f"No 'h1.post-title' found for {url}")
        return None
    title = get_cleaned_text(title_tag)

    # 3. Determine subdomain (Defaulting to Cooking for this site)
    subdomain = "Cooking"
    # Optional: Add logic here to check breadcrumbs if non-cooking content exists
    # breadcrumb = article_container.select_one('div.breadcrumb')
    # if breadcrumb and 'some_non_cooking_keyword' in breadcrumb.get_text():
    #     subdomain = "OtherCategory"

    # 4. Get the main content area
    content_area = article_container.select_one('div.post-content')
    if not content_area:
        print(f"No 'div.post-content' found for {url}")
        return None

    # 5. --- Decompose junk ---
    selectors_to_remove = [
        '.post-meta',                   # Author/Date line under title
        'p.disclosure',                 # Affiliate link disclosure
        '.dpsp-content-wrapper',        # Share buttons (top and bottom)
        '.adthrive',                    # Ad placeholders / Video player
        '.adthrive-auto-injected-player-container', # Specific video player container
        '.slick-on-page',               # Ad related
        '.slick-story-viewer-panel',    # Ad related
        '.slick-inline-search-panel',   # Ad related search panel
        '.post-cats',                   # Category links at the bottom
        '.breadcrumb',                  # Breadcrumb navigation
        '.jumpbuttons',                 # Jump to recipe button container within post-meta
        'a.button.tasty-recipes-print-button', # Standalone print button before recipe card
        '.tasty-recipes-jump-target',    # Invisible jump target
        'svg[aria-hidden="true"]',       # Remove decorative SVGs like stars
        # Add any other global selectors here
    ]
    for selector in selectors_to_remove:
        # Search within the whole article as some elements are outside content_area
        for element in article_container.select(selector):
            element.decompose()


    # 6. --- Handle Recipe Card ---
    recipe_text = ""
    # Find the recipe card *within the potentially modified content_area*
    recipe_card_container = content_area.select_one('div.tasty-recipes') # Target Tasty Recipes container
    if recipe_card_container:
        recipe_text = parse_tasty_recipes_card(recipe_card_container)
        recipe_card_container.decompose() # Remove after parsing


    # 7. --- Extract the main article text ---
    content_parts = []
    # Iterate through direct children of content_area
    for element in content_area.children:
        if not isinstance(element, Tag):
            continue

        # Skip known containers we don't want to iterate inside further
        if 'tasty-recipes' in element.get('class', []):
             continue # Already processed recipe card

        # Handle text tags (p, h2, h3, h4) and check for images inside
        if element.name in ['p', 'h2', 'h3', 'h4']:
            img = element.find('img')
            if img:
                img_url = img.get('data-lazy-src') or img.get('data-src') or img.get('src')
                width = img.get('width')
                height = img.get('height')
                try:
                    # Added check for data-pin-url as another potential source attr
                    if not img_url and 'data-pin-url' in img.attrs:
                       pin_url_img = img.attrs.get('data-pin-url', '')
                       # Try to extract image URL from pin URL if it seems valid
                       match = re.search(r'tp_image_id=(\d+)', pin_url_img)
                       if match: # If an ID is found, we might need more logic, assume src is best for now
                          pass # Keep existing logic prio
                    # Filter small images and gravatars
                    if img_url and img_url.startswith('http') and (not width or int(width) > 30) and (not height or int(height) > 30) and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")
                except (ValueError, TypeError):
                    if img_url and img_url.startswith('http') and 'gravatar.com' not in img_url:
                        content_parts.append(f"[image: {img_url}]")

            text = get_cleaned_text(element)
            if text: # Only append text if it's not empty
                content_parts.append(text)

        # Handle lists
        elif element.name in ['ul', 'ol']:
            for li in element.find_all('li', recursive=False):
                li_text = get_cleaned_text(li)
                if li_text:
                    content_parts.append(f"- {li_text}")

        # Handle figures (single images and galleries)
        elif element.name == 'figure' and ('wp-block-image' in element.get('class', []) or 'wp-block-gallery' in element.get('class', [])):
            images = element.find_all('img')
            for img in images:
                img_url = img.get('data-lazy-src') or img.get('data-src') or img.get('src')
                # Added check for data-pin-url
                if not img_url and 'data-pin-url' in img.attrs:
                    pin_url_img = img.attrs.get('data-pin-url', '')
                    match = re.search(r'tp_image_id=(\d+)', pin_url_img)
                    # For now, let's just stick to src/data-src attributes if possible
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


    # 8. --- Combine, Clean, and Format ---
    article_text = '\n'.join(filter(None, content_parts))
    full_content_text = f"{article_text}\n\n{recipe_text}".strip() # Add recipe if found

    normalized_title = normalize_text(title)
    cleaned_content = anonymize_text(normalize_text(full_content_text))

    text_for_length_check = re.sub(r'\[image: [^\]]+\]', '', cleaned_content)
    min_length = 100 if recipe_text else 150 # Shorter min length if recipe card is present
    if len(text_for_length_check) < min_length:
        print(f"Skipped {url}: Content too short ({len(text_for_length_check)} chars, needed {min_length}) after cleaning.")
        return None

    processing_date = datetime.now().strftime("%Y-%m-%d")

    domain_info = {
        "domain": "daily_life",
        # Assuming Cooking for this site based on examples
        "subdomain": "Cooking Tips, food knowledge, food preservation"
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
            # Give page a moment longer to potentially finish rendering images/lazy content
            page.wait_for_timeout(1500) # Increased wait time slightly
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