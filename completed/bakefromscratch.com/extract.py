# scraper_immediate_write.py

import requests
from bs4 import BeautifulSoup
import time

def scrape_category(base_url, file_handler, tracked_links_set):
    """
    Scrapes a category and writes links directly to the provided file handler.
    
    Args:
        base_url (str): The starting URL of the category.
        file_handler: The file object to write to.
        tracked_links_set (set): A set to track duplicates found during this run.
    """
    page_number = 1
    
    while True:
        if page_number == 1:
            current_url = base_url
        else:
            current_url = f"{base_url}page/{page_number}/"
            
        print(f"Scraping page {page_number} of '{base_url}'...")
        
        try:
            response = requests.get(current_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            if response.status_code == 404:
                print(f"Page {page_number} not found. Reached the end of this category.\n")
                break
            
            response.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching {current_url}: {e}\n")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        article_headers = soup.find_all('h3', class_='entry-title td-module-title')
        
        if not article_headers and page_number > 1:
            print("No more articles found. Reached the end of this category.\n")
            break
            
        new_links_found_on_page = 0
        for header in article_headers:
            link_tag = header.find('a')
            if link_tag and 'href' in link_tag.attrs:
                link = link_tag['href']
                # Check if we've already found and written this link during this run
                if link not in tracked_links_set:
                    # Write to file immediately
                    file_handler.write(link + '\n')
                    # Add to our set to prevent writing duplicates
                    tracked_links_set.add(link)
                    new_links_found_on_page += 1
        
        if new_links_found_on_page > 0:
            print(f"  Found and wrote {new_links_found_on_page} new link(s).")

        page_number += 1
        time.sleep(1)


def main():
    """
    Main function to run the scraper.
    """
    category_urls = [
        "https://bakefromscratch.com/category/recipes/",
        "https://bakefromscratch.com/category/blog/"
    ]
    
    output_filename = "bakefromscratch_links.txt"
    # This set prevents writing duplicate links if they appear on multiple pages
    tracked_links_this_run = set()
    
    # Open the file once in write mode ('w'). 
    # The 'with' statement ensures it's properly closed even if errors occur.
    try:
        with open(output_filename, 'w', encoding='utf-8') as file_handler:
            print(f"Opened '{output_filename}' for writing. Starting scrape...")
            # Scrape each category, passing the file handler
            for url in category_urls:
                scrape_category(url, file_handler, tracked_links_this_run)
                
        print(f"\nScraping complete. Found and saved {len(tracked_links_this_run)} unique links.")
        print(f"Data saved to '{output_filename}'")
        
    except IOError as e:
        print(f"Error: Could not write to file '{output_filename}': {e}")


if __name__ == "__main__":
    main()