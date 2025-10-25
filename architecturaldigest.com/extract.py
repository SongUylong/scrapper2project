import requests
from bs4 import BeautifulSoup
import time
import os # <-- Added for file handling

# --- Configuration ---
BASE_URL = 'https://www.architecturaldigest.com'
CATEGORIES = ['architecture-design', 'shopping', 'celebrity-style', 'ad-it-yourself', 'adpro', 'adpro/newsroom', 'adpro/grow-your-business', 'adpro/the-report', ''] 
OUTPUT_FILE = 'architecturaldigest_links.txt'
STATE_FILE = 'scraper_state.txt' # <-- New file to save progress
# --- End Configuration ---

# --- MODIFICATION: Load existing links ---
# A set to keep track of links we've already saved to avoid duplicates
saved_links = set()
if os.path.exists(OUTPUT_FILE):
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                saved_links.add(line.strip())
        print(f"Loaded {len(saved_links)} existing links from {OUTPUT_FILE}.")
    except IOError as e:
        print(f"Error reading {OUTPUT_FILE}: {e}")
else:
    print(f"No existing {OUTPUT_FILE} found. Starting fresh.")
# --- END MODIFICATION ---

# --- MODIFICATION: Load last state ---
start_category = None
start_page = 1
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state_data = f.read().strip()
            if state_data:
                start_category, page_str = state_data.split(',')
                start_page = int(page_str)
                print(f"Resuming from category '{start_category}', page {start_page}")
    except Exception as e:
        print(f"Warning: Could not read state file ({e}). Starting from beginning.")
        start_category = None
        start_page = 1
# --- END MODIFICATION ---


# Use a session for connection pooling
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})

# --- MODIFICATION: Find starting category ---
found_start_category = (start_category is None)

for category in CATEGORIES:
    # This block skips categories until we find the one we left off on
    if not found_start_category:
        if category == start_category:
            found_start_category = True # Start processing from this category
        else:
            print(f"\n--- Skipping Category: {category} (already processed) ---")
            continue
    # --- END MODIFICATION ---

    # Handle the empty string category (homepage)
    if category == '':
        print(f"\n--- Scraping Category: Homepage ---")
    else:
        print(f"\n--- Scraping Category: {category} ---")
        
    page = start_page # Start from page 1 or the resumed page
    
    while True:
        # --- MODIFICATION: Save current state *before* fetching ---
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                f.write(f"{category},{page}")
        except IOError as e:
            print(f"Warning: Could not save state to {STATE_FILE}. {e}")
        # --- END MODIFICATION ---

        # Construct the correct URL based on the page number
        if page == 1:
            current_url = f"{BASE_URL}/{category}"
        else:
            current_url = f"{BASE_URL}/{category}?page={page}"
            
        print(f"Fetching page {page}: {current_url}")
        
        try:
            response = session.get(current_url)
            # Raise an error for bad responses (4xx or 5xx)
            response.raise_for_status() 
        except requests.exceptions.RequestException as e:
            print(f"Error fetching URL {current_url}: {e}")
            break # Stop scraping this category if a page fails

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Find ALL main content grids, not just the first one.
        content_blocks = soup.find_all('div', class_='grid-layout__content')
        
        # This will hold all articles from ALL content blocks
        all_article_containers = []
        
        if not content_blocks:
            print(f"No 'grid-layout__content' blocks found. Assuming no articles.")
        else:
            # 2. Loop through each content block found
            for content_block in content_blocks:
                # Find all article items *within this specific block*
                articles_in_block = content_block.find_all('div', class_='SummaryItemWrapper-ircKXK')
                # Add them to our master list
                all_article_containers.extend(articles_in_block)
        
        if not all_article_containers:
            print(f"No more articles found for '{category}'. Moving to next category.")
            break # Exit the while loop for this category

        links_found_on_page = 0
        
        try:
            # Open the file in 'append' mode to write links as we find them
            # We no longer need the initial 'w' write, as we load existing links
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                # Loop through the combined list of all articles
                for item in all_article_containers:
                    # Find the specific headline link you pointed out
                    link_tag = item.find('a', class_='summary-item__hed-link')
                    
                    if link_tag and link_tag.get('href'):
                        href = link_tag['href']
                        
                        # Build the full URL
                        if href.startswith('http'):
                            full_url = href
                        else:
                            # Handle relative URLs like '/story/...'
                            full_url = BASE_URL + href
                        
                        # Write to file only if it's a new link
                        if full_url not in saved_links:
                            f.write(full_url + '\n')
                            saved_links.add(full_url)
                            links_found_on_page += 1

            print(f"Found and saved {links_found_on_page} new links from page {page}.")
            
            # If a page returns 0 *new* links, we can assume we're done
            if links_found_on_page == 0 and page > 1:
                print("No new links found on this page. Ending category.")
                break

        except IOError as e:
            print(f"Error writing to file: {e}")
            break # Stop if we can't write to the file
            
        page += 1
        time.sleep(1) # Be polite to the server, wait 1 second between requests
    
    # --- MODIFICATION: Reset start_page for the *next* category ---
    start_page = 1
    # --- END MODIFICATION ---

# --- MODIFICATION: Clean up state file on completion ---
print(f"\n--- Scraping Complete ---")
if os.path.exists(STATE_FILE):
    try:
        os.remove(STATE_FILE)
        print(f"Successfully removed state file {STATE_FILE}.")
    except OSError as e:
        print(f"Error: Could not remove state file {STATE_FILE}. {e}")
# --- END MODIFICATION ---

print(f"Total unique links saved to {OUTPUT_FILE}: {len(saved_links)}")