import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from typing import Set

# --- Core Libraries ---
import aiofiles
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError

# --- Configuration ---
WEBSITE_NAME = "acozykitchen.com"
DELIVERY_VERSION = "V1.0"
CONCURRENT_WORKERS = 1 # Set to 1 for single-article scraping
MIN_CHAR_COUNT = 200
USER_AGENT = "Mozilla/5.0 (Windows NT 1.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# --- Single Article URL for Testing ---
# ⚠️ Replace this with a real article URL from acozykitchen.com to test 
SINGLE_ARTICLE_URL = "https://www.acozykitchen.com/pumpkin-cream-cheese-muffins"

# --- File Paths for State Management ---
LINKS_FILE = "test_link_to_scrape.jsonl"
OUTPUT_FILE = f"test_data.jsonl" # Changed output file for clarity

# --- Helper Functions ---

def generate_id(url: str) -> str:
    """Generates an MD5 hash for a given URL."""
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def clean_simple_text(text: str) -> str:
    """Removes extra whitespace, normalizes line breaks, and removes emojis (and the preceding space)."""
    if not text: return ""
    cleaned = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    cleaned = re.sub(r'\n{2,}', '\n', cleaned)
    
    # Define the emoji pattern
    emoji_chars = (
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
    )
    # Emoji Removal including preceding space
    emoji_pattern_with_space = re.compile(
        r' ?[' + emoji_chars + r']+', 
        flags=re.UNICODE
    )
    cleaned = emoji_pattern_with_space.sub(r'', cleaned)
    
    return cleaned

# --- Core Scraping and State Management Functions ---

# Removed collect_all_article_links as it is no longer needed.

async def get_scraped_urls(file_path: str) -> Set[str]:
    """Reads the output file to find which URLs have already been successfully scraped."""
    scraped_urls = set()
    if not os.path.exists(file_path):
        return scraped_urls
    
    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
        async for line in f:
            try:
                data = json.loads(line)
                url = data.get("meta", {}).get("data_info", {}).get("url")
                if url: scraped_urls.add(url)
            except (json.JSONDecodeError, KeyError):
                continue
    return scraped_urls


async def scrape_article_page(page: Page, url: str, lock: asyncio.Lock):
    """Scrapes, processes, and saves data from a single article page."""
    try:
        print(f"🌍 Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        article_data = await page.evaluate("""() => {
            const getBestSrc = (el) => {
                if (!el) return '';
                let src = el.getAttribute('data-lazy-src') || el.getAttribute('src') || '';
                const srcset = el.getAttribute('data-lazy-srcset') || el.getAttribute('srcset');
                if (srcset) {
                    const largestSrc = srcset.split(',').map(s => {
                        const parts = s.trim().split(' ');
                        return { url: parts[0], width: parseInt(parts[1]?.replace('w', '')) || 0 };
                    }).sort((a, b) => b.width - a.width)[0];
                    src = largestSrc.url;
                }
                return src.startsWith('data:image') ? '' : src;
            };

            // Helper to parse the structured recipe card
            const parseRecipeCard = (container) => {
                const recipeParts = [];
                const recipeTitle = container.querySelector('.wprm-recipe-name')?.textContent.trim();
                if (recipeTitle) recipeParts.push(`${recipeTitle}`);
                
                // --- Equipment ---
                const equipmentSection = container.querySelector('.wprm-recipe-equipment-container');
                if (equipmentSection) {
                    recipeParts.push(`Equipment`);
                    const items = Array.from(equipmentSection.querySelectorAll('.wprm-recipe-equipment-name'))
                                       .map(el => `- ${el.textContent.trim()}`);
                    if (items.length > 0) recipeParts.push(items.join('\\n'));
                }

                // --- Ingredients ---
                const ingredientsSection = container.querySelector('.wprm-recipe-ingredients-container');
                if (ingredientsSection) {
                    recipeParts.push(`Ingredients`);
                    const groups = ingredientsSection.querySelectorAll('.wprm-recipe-ingredient-group');
                    groups.forEach(group => {
                        const groupTitle = group.querySelector('.wprm-recipe-ingredient-group-name');
                        if (groupTitle) recipeParts.push(`${groupTitle.textContent.trim()}`);
                        const items = Array.from(group.querySelectorAll('.wprm-recipe-ingredient'))
                                           .map(el => `- ${el.textContent.replace(/▢/g, '').trim()}`);
                        if (items.length > 0) recipeParts.push(items.join('\\n'));
                    });
                }
                
                // --- Instructions ---
                const instructionsSection = container.querySelector('.wprm-recipe-instructions-container');
                if (instructionsSection) {
                    recipeParts.push(` Instructions`);
                    const groups = instructionsSection.querySelectorAll('.wprm-recipe-instruction-group');
                    groups.forEach(group => {
                        const groupTitle = group.querySelector('.wprm-recipe-instruction-group-name');
                        if (groupTitle) recipeParts.push(`${groupTitle.textContent.trim()}`);
                        const items = Array.from(group.querySelectorAll('.wprm-recipe-instruction-text'))
                                           .map((el, index) => `${index + 1}. ${el.textContent.trim()}`);
                        if (items.length > 0) recipeParts.push(items.join('\\n'));
                    });
                }
                
                // --- Notes ---
                const notesSection = container.querySelector('.wprm-recipe-notes-container .wprm-recipe-notes');
                if (notesSection) {
                    recipeParts.push(` Notes`);
                    const noteText = Array.from(notesSection.querySelectorAll('p, li'))
                                          .map(el => el.textContent.trim())
                                          .join('\\n');
                    if (noteText) recipeParts.push(noteText);
                }

                return recipeParts.join('\\n\\n');
            };

            const articleContainer = document.querySelector('article.type-post');
            if (!articleContainer) return { error: "Main article container not found." };
            
            const titleElement = articleContainer.querySelector('h1.entry-title');
            const title = titleElement ? titleElement.textContent.trim() : "No Title Found";

            const contentContainer = articleContainer.querySelector('div.entry-content');
            if (!contentContainer) return { error: "Entry content container not found." };
            
            // Clone the container to modify it without affecting the page
            const clone = contentContainer.cloneNode(true);

            // --- REMOVE NOISY ELEMENTS ---
            clone.querySelectorAll('div[class*="adthrive"], div.aff-disc, div[id*="video-container"], section.block-post-listing, .wp-block-yoast-seo-table-of-contents').forEach(el => el.remove());
            clone.querySelectorAll('p').forEach(p => {
                if (p.textContent.includes('star rating')) p.remove();
            });
            // Remove the post header content inside entry-content
             const postHeader = clone.querySelector('div.post-header');
             if (postHeader) postHeader.remove();

            const contentParts = [];
            const textOnlyParts = [];

            // Iterate through the cleaned nodes to preserve order
            for (const node of clone.childNodes) {
                if (node.nodeType !== Node.ELEMENT_NODE) continue; // Skip non-element nodes

                const tagName = node.tagName.toLowerCase();
                const text = node.textContent.trim();

                if (['p', 'h2', 'h3', 'h4'].includes(tagName)) {
                    if (text) {
                        contentParts.push(text);
                        textOnlyParts.push(text);
                    }
                } else if (tagName === 'figure' && node.matches('.wp-block-image')) {
                    const img = node.querySelector('img');
                    const imgSrc = getBestSrc(img);
                    if (imgSrc) contentParts.push(`[image: ${imgSrc}]`);
                } else if (['ul', 'ol'].includes(tagName)) {
                    const listItems = Array.from(node.querySelectorAll('li'))
                        .map(li => `- ${li.textContent.trim()}`)
                        .join('\\n');
                    if (listItems) {
                        contentParts.push(listItems);
                        textOnlyParts.push(listItems);
                    }
                } else if (tagName === 'div' && node.matches('.block-tip')) {
                     const tipTitle = node.querySelector('h2')?.textContent.trim() || 'Recipe Tip';
                     const tipItems = Array.from(node.querySelectorAll('li'))
                        .map(li => `- ${li.textContent.trim()}`)
                        .join('\\n');
                    if (tipItems) {
                        const fullTip = ` ${tipTitle}\\n${tipItems}`;
                        contentParts.push(fullTip);
                        textOnlyParts.push(fullTip);
                    }
                } else if (tagName === 'div' && node.matches('.schema-faq')) {
                    const faqTitle = node.querySelector('h2')?.textContent.trim() || 'FAQ';
                    contentParts.push(`${faqTitle}`);
                    textOnlyParts.push(faqTitle);
                    
                    node.querySelectorAll('.schema-faq-section').forEach(section => {
                        const question = section.querySelector('.schema-faq-question')?.textContent.trim();
                        const answer = section.querySelector('.schema-faq-answer')?.textContent.trim();
                        if (question && answer) {
                            const fullQA = ` ${question}\\n${answer}`;
                            contentParts.push(fullQA);
                            textOnlyParts.push(fullQA);
                        }
                    });
                } else if (node.id.startsWith('wprm-recipe-container')) {
                    const recipeText = parseRecipeCard(node);
                     if (recipeText) {
                        contentParts.push(recipeText);
                        textOnlyParts.push(recipeText);
                    }
                }
            }

            const fullContent = contentParts.join('\\n\\n');
            const textOnlyContent = textOnlyParts.join('\\n\\n');

            return { title, fullContent, textOnlyContent };
        }""")
        
        if not article_data or article_data.get("error"):
            error_msg = article_data.get('error', "Essential content not found")
            print(f"🔻 Skipped '{url}': {error_msg}")
            return

        full_content = article_data['fullContent']
        title = article_data['title']
        text_for_char_count = re.sub(r'\[image:.*?\]', '', article_data['textOnlyContent']).strip()

        if len(text_for_char_count) < MIN_CHAR_COUNT:
            print(f"🔻 Skipped '{title[:40]}...': Not enough content ({len(text_for_char_count)} chars).")
            return

        cleaned_content = clean_simple_text(full_content)
        
        final_data = {
            "ID": generate_id(url),
            "Text": f"{title}\n{cleaned_content}",
            "meta": {
                "data_info": {
                    "lang": "en", "url": url, "source": WEBSITE_NAME,
                    "type": "Article", "processing_date": datetime.now().strftime("%Y-%m-%d"),
                    "delivery_version": DELIVERY_VERSION, "title": title, "content": cleaned_content,
                    "content_info": {
                        "domain": "daily_life",
                        "subdomain": "Cooking Tips, food knowledge, food preservation"
                    }
                }
            }
        }
        
        async with lock:
            async with aiofiles.open(OUTPUT_FILE, mode='a', encoding='utf-8') as f:
                await f.write(json.dumps(final_data, ensure_ascii=False) + "\n")
        
        print(f"✅ Success: Saved '{title[:40]}...' (Length: {len(text_for_char_count)}) to {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ Error on article '{url}': {str(e)[:150]}...")


async def worker(context: BrowserContext, queue: asyncio.Queue, lock: asyncio.Lock):
    """A worker that continuously fetches tasks from the queue and scrapes them."""
    while True:
        url = await queue.get()
        page = await context.new_page()
        try:
            # Abort non-essential resources to speed up single-page load
            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["stylesheet", "font", "media", "script"] else route.continue_())
            await scrape_article_page(page, url, lock)
        finally:
            await page.close()
            queue.task_done()


async def main():
    """Main orchestrator for the single-article scraping process."""
    print(f"⚙️ Running in single-article mode for: {SINGLE_ARTICLE_URL}")
    async with async_playwright() as p:
        # Use Chromium for stability
        browser = await p.chromium.launch(headless=True)

        scraped_urls = await get_scraped_urls(OUTPUT_FILE)
        
        if SINGLE_ARTICLE_URL in scraped_urls:
             print("✅ Article already scraped. Nothing to do.")
             await browser.close()
             return

        print("\n🚀 Starting single-article scraping phase...")

        file_lock = asyncio.Lock()
        queue = asyncio.Queue()
        queue.put_nowait(SINGLE_ARTICLE_URL) # Add the single URL to the queue

        worker_contexts = [await browser.new_context(user_agent=USER_AGENT) for _ in range(CONCURRENT_WORKERS)]
        # Start a single worker since CONCURRENT_WORKERS is set to 1, but keep the structure
        tasks = [asyncio.create_task(worker(worker_contexts[i], queue, file_lock)) for i in range(CONCURRENT_WORKERS)]

        await queue.join()

        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for ctx in worker_contexts: await ctx.close()
        await browser.close()

    print(f"\n✨ Scraping complete. Data saved to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    # Ensure the old links file doesn't trigger the multi-scrape logic unexpectedly
    if os.path.exists(LINKS_FILE):
        print(f"⚠️ Note: '{LINKS_FILE}' exists but is ignored in single-article mode.")
    
    # Clear the single article output file if it exists to prevent re-skipping during a test run
    # os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    # if os.path.exists(OUTPUT_FILE):
    #     os.remove(OUTPUT_FILE)
    #     print(f"🗑️ Cleared previous '{OUTPUT_FILE}' for fresh run.")
        
    asyncio.run(main())