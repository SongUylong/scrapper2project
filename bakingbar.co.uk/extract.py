# scraper_bakingbar.py

import requests
from bs4 import BeautifulSoup
import time

def scrape_category(category_url, file_handler, tracked_links_set):
    """
    Scrapes all article links from a given category, handling pagination.

    Args:
        category_url (str): The URL of the category to scrape.
        file_handler: The file object opened for writing.
        tracked_links_set (set): A set to prevent duplicate link writes.
    """
    page_number = 1
    
    while True:
        if page_number == 1:
            current_url = category_url
        else:
            # Ensure a trailing slash before adding the page number
            base_url = category_url.rstrip('/') + '/'
            current_url = f"{base_url}page/{page_number}/"
            
        print(f"Scraping page {page_number} of '{category_url}'...")
        
        try:
            response = requests.get(current_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            # A 404 error means we've reached the last page
            if response.status_code == 404:
                print(f"  -> Page {page_number} not found. Finished this category.\n")
                break
            
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            print(f"  -> An error occurred while fetching {current_url}: {e}\n")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all h2 tags with the specific class for article titles
        article_headings = soup.find_all('h2', class_='cm-entry-title')
        
        # If no headings are found on a page (after the first one), we assume we're done.
        if not article_headings and page_number > 1:
            print("  -> No more articles found. Finished this category.\n")
            break

        new_links_on_page = 0
        for heading in article_headings:
            link_tag = heading.find('a')
            if link_tag and 'href' in link_tag.attrs:
                link = link_tag['href']
                # Write the link only if it's new for this session
                if link not in tracked_links_set:
                    file_handler.write(link + '\n')
                    tracked_links_set.add(link)
                    new_links_on_page += 1
        
        if new_links_on_page > 0:
            print(f"  -> Found and wrote {new_links_on_page} new link(s).")
        else:
            print("  -> No new links were found on this page.")

        page_number += 1
        time.sleep(1) # Wait a second between requests to be polite

def main():
    """
    Main function to run the scraper.
    """
    # List of all the category URLs to be scraped
    category_urls_to_scrape = [
        "https://www.bakingbar.co.uk/category/top-chef-interviews/",
        "https://www.bakingbar.co.uk/category/short-stay-guides/",
        "https://www.bakingbar.co.uk/category/reviews/",
        "https://www.bakingbar.co.uk/category/news-articles/",
        "https://www.bakingbar.co.uk/category/gift-guides/",
        "https://www.bakingbar.co.uk/category/drinks/",
        "https://www.bakingbar.co.uk/category/cakes/",
        "https://www.bakingbar.co.uk/category/smart-home/",
        "https://www.bakingbar.co.uk/category/competitions/"
    ]
    
    output_filename = "bakingbar_links.txt"
    tracked_links = set()
    
    try:
        # Open the file once with a writing stream
        with open(output_filename, 'w', encoding='utf-8') as file:
            print(f"Opened '{output_filename}' for writing. Starting scrape...\n")
            
            # Scrape each category URL from the list
            for url in category_urls_to_scrape:
                scrape_category(url, file, tracked_links)
                
        print(f"\nScraping complete.")
        print(f"Found and saved a total of {len(tracked_links)} unique links to '{output_filename}'.")
        
    except IOError as e:
        print(f"Fatal Error: Could not write to file '{output_filename}': {e}")

if __name__ == "__main__":
    main()