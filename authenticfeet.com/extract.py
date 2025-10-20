# scraper.py

import requests
from bs4 import BeautifulSoup
import time

def scrape_category(base_url, all_links_set):
    """
    Scrapes a category page by page to find all article links.
    
    Args:
        base_url (str): The starting URL of the category.
        all_links_set (set): A set to store the unique URLs found.
    """
    page_number = 1
    
    while True:
        # Construct the URL for the current page
        if page_number == 1:
            current_url = base_url
        else:
            current_url = f"{base_url}page/{page_number}/"
            
        print(f"Scraping page {page_number} of '{base_url}'...")
        
        try:
            # Send a request to the URL
            response = requests.get(current_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            # If we get a 404 error, it means the page doesn't exist, so we're done.
            if response.status_code == 404:
                print(f"Page {page_number} not found. Reached the end of this category.\n")
                break
            
            # Raise an error for other bad status codes (e.g., 500, 403)
            response.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            print(f"An error occurred while fetching {current_url}: {e}\n")
            break

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all h3 tags with the specified class
        article_headers = soup.find_all('h3', class_='entry-title td-module-title')
        
        # If no articles are found on a page (after the first one), we assume we've reached the end.
        if not article_headers and page_number > 1:
            print("No more articles found. Reached the end of this category.\n")
            break
            
        # Extract the href from the 'a' tag within each h3
        for header in article_headers:
            link_tag = header.find('a')
            if link_tag and 'href' in link_tag.attrs:
                all_links_set.add(link_tag['href'])

        page_number += 1
        time.sleep(1) # Be polite to the server by waiting a second between requests


def main():
    """
    Main function to run the scraper.
    """
    # List of category URLs to scrape
    category_urls = [
        "https://bakefromscratch.com/category/recipes/",
        "https://bakefromscratch.com/category/blog/"
    ]
    
    # Use a set to automatically handle duplicate links
    all_article_links = set()
    output_filename = "bakefromscratch_links.txt"
    
    # Scrape each category
    for url in category_urls:
        scrape_category(url, all_article_links)
        
    print(f"Scraping complete. Found {len(all_article_links)} unique article links.")
    
    # Save the collected links to a text file
    with open(output_filename, 'w', encoding='utf-8') as f:
        # Sort the links alphabetically for a clean output
        for link in sorted(list(all_article_links)):
            f.write(link + '\n')
            
    print(f"All links have been successfully saved to '{output_filename}'")


if __name__ == "__main__":
    main()