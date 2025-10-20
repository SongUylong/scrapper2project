# scraper_bakeplaysmile.py

import requests
from bs4 import BeautifulSoup
import time

def get_category_links(index_url):
    """
    Scrapes the main recipe index to get all category URLs.

    Args:
        index_url (str): The URL of the main recipe index page.

    Returns:
        list: A list of category page URLs, or an empty list if an error occurs.
    """
    print(f"Fetching category links from: {index_url}")
    category_links = []
    try:
        response = requests.get(index_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status() # Check for any request errors

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the specific 'ul' that contains the category links
        category_list = soup.find('ul', class_='feast-category-index-list')
        
        if not category_list:
            print("Could not find the category list on the page.")
            return []

        # Find all 'a' tags within that list
        links = category_list.find_all('a')
        for link in links:
            if link and 'href' in link.attrs:
                category_links.append(link['href'])
        
        print(f"Found {len(category_links)} category links to scrape.\n")
        return category_links

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the index page {index_url}: {e}")
        return []

def scrape_recipes_in_category(category_url, file_handler, tracked_links_set):
    """
    Scrapes all recipe links from a category, handling pagination and writing immediately.

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
            # Append a trailing slash if it's missing before adding the page number
            base_url = category_url.rstrip('/') + '/'
            current_url = f"{base_url}page/{page_number}/"
            
        print(f"Scraping page {page_number} of '{category_url}'...")
        
        try:
            response = requests.get(current_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            if response.status_code == 404:
                print(f"  -> Page {page_number} not found. Reached the end of this category.\n")
                break
            
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            print(f"  -> An error occurred while fetching {current_url}: {e}\n")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the main list containing the recipe links for this category
        recipe_list = soup.find('ul', class_='fsri-list')
        
        if not recipe_list:
            print(f"  -> No recipe list found on page {page_number}. Moving to next category.\n")
            break

        # Extract all 'a' tags within the recipe list
        recipe_links = recipe_list.find_all('a')
        
        if not recipe_links and page_number > 1:
            print("  -> No more recipe links found. Reached the end of this category.\n")
            break

        new_links_on_page = 0
        for link_tag in recipe_links:
            if 'href' in link_tag.attrs:
                link = link_tag['href']
                if link not in tracked_links_set:
                    file_handler.write(link + '\n')
                    tracked_links_set.add(link)
                    new_links_on_page += 1
        
        if new_links_on_page > 0:
            print(f"  -> Found and wrote {new_links_on_page} new recipe link(s).")
        else:
            print("  -> No new links found on this page.")


        page_number += 1
        time.sleep(1) # Be polite to the server

def main():
    """
    Main function to orchestrate the scraping process.
    """
    start_url = "https://bakeplaysmile.com/recipe-index/"
    output_filename = "bakeplaysmile_links.txt"
    
    # First, get all the category links from the main index
    category_urls = get_category_links(start_url)
    
    if not category_urls:
        print("No categories found. Exiting.")
        return

    # A set to track all links found during this session to avoid duplicates
    tracked_links_this_run = set()
    
    try:
        # Open a single writing stream for the entire process
        with open(output_filename, 'w', encoding='utf-8') as file_handler:
            # Now, iterate through each category and scrape its recipes
            for url in category_urls:
                scrape_recipes_in_category(url, file_handler, tracked_links_this_run)
                
        print(f"\nScraping complete. A total of {len(tracked_links_this_run)} unique links were found.")
        print(f"All links have been saved to '{output_filename}'")
        
    except IOError as e:
        print(f"Fatal Error: Could not open or write to file '{output_filename}': {e}")

if __name__ == "__main__":
    main()