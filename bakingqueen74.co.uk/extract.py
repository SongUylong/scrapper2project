# scraper_bakingqueen74_final.py

import requests
from bs4 import BeautifulSoup
import time

def get_category_links(index_url):
    """
    Scrapes the main recipe index for lists with the class 'feast-category-index-list'
    to get all category URLs.

    Args:
        index_url (str): The URL of the main recipe index page.

    Returns:
        list: A list of unique category page URLs.
    """
    print(f"Fetching category links from: {index_url}")
    category_links = set() 
    try:
        response = requests.get(index_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # --- CORRECTION START ---
        # Find all <ul> lists that have the specific class for CATEGORIES.
        # This will correctly ignore the recipe lists (fsri-list).
        category_lists = soup.find_all('ul', class_='feast-category-index-list')
        
        if not category_lists:
            print("Could not find any <ul class='feast-category-index-list'> containers.")
            return []

        # Iterate through each category list found
        for ulist in category_lists:
            # Find all 'a' tags within that list
            links = ulist.find_all('a')
            for link in links:
                if 'href' in link.attrs:
                    category_links.add(link['href'])
        # --- CORRECTION END ---
        
        print(f"Found {len(category_links)} unique category links to scrape.\n")
        return list(category_links)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the index page {index_url}: {e}")
        return []

def scrape_recipes_in_category(category_url, file_handler, tracked_links_set):
    """
    Scrapes all recipe links from a category, handling pagination and writing immediately.
    """
    page_number = 1
    
    while True:
        if page_number == 1:
            current_url = category_url
        else:
            base_url = category_url.rstrip('/') + '/'
            current_url = f"{base_url}page/{page_number}/"
            
        print(f"Scraping page {page_number} of '{category_url}'...")
        
        try:
            response = requests.get(current_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            if response.status_code == 404:
                print(f"  -> Page {page_number} not found. Finished this category.\n")
                break
            
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            print(f"  -> An error occurred while fetching {current_url}: {e}\n")
            break

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # This selector for the recipe list is still correct for the category pages.
        recipe_list = soup.find('ul', class_='fsri-list')
        
        if not recipe_list:
            print(f"  -> No recipe list found on page {page_number}. Ending this category.\n")
            break

        recipe_links = recipe_list.find_all('a')
        
        if not recipe_links and page_number > 1:
            print("  -> No more recipe links found. Finished this category.\n")
            break

        new_links_found = 0
        for link_tag in recipe_links:
            if 'href' in link_tag.attrs:
                link = link_tag['href']
                if link not in tracked_links_set:
                    file_handler.write(link + '\n')
                    tracked_links_set.add(link)
                    new_links_found += 1
        
        if new_links_found > 0:
            print(f"  -> Found and wrote {new_links_found} new recipe link(s).")
        else:
            print("  -> No new links found on this page.")

        page_number += 1
        time.sleep(1)

def main():
    """
    Main function to run the scraper.
    """
    start_url = "https://bakingqueen74.co.uk/recipe-index-3/"
    output_filename = "bakingqueen74_links.txt"
    
    category_urls = get_category_links(start_url)
    
    if not category_urls:
        print("Scraping stopped because no category URLs were found.")
        return

    tracked_links = set()
    
    try:
        with open(output_filename, 'w', encoding='utf-8') as file_handler:
            for url in category_urls:
                scrape_recipes_in_category(url, file_handler, tracked_links)
                
        print(f"\nScraping complete. Found and saved {len(tracked_links)} unique recipe links.")
        print(f"All links have been written to '{output_filename}'")
        
    except IOError as e:
        print(f"Fatal Error: Could not open or write to file '{output_filename}': {e}")

if __name__ == "__main__":
    main()