import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import time

def get_last_page_number(url):
    """
    Fetches the first page to determine the total number of pages from the pagination controls.
    
    """
    try:
        print("Finding the total number of pages...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.text, 'html.parser')
        
        pagination = soup.find('div', class_='pagination')
        if not pagination:
            print("Pagination not found. Assuming a single page.")
            return 1
        
        page_links = pagination.find_all('a')
        if not page_links or len(page_links) < 2:
            return 1

        # The link to the last page is the one before the "Next" arrow's link
        last_page_href = page_links[-2].get('href')
        
        # Parse the URL to extract the 'page' number
        parsed_url = urlparse(last_page_href)
        query_params = parse_qs(parsed_url.query)
        
        if 'page' in query_params:
            last_page = int(query_params['page'][0])
            print(f"Found {last_page} pages to scrape.")
            return last_page
        else:
            return 1
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the website to find total pages: {e}")
        return None
    except (AttributeError, IndexError, ValueError):
        print("Could not parse the last page number. Scraping might be incomplete.")
        return 1

def scrape_all_blog_links(base_url, total_pages):
    """
    Loops through each page of the blog, scraping all unique article links.
    """
    all_article_links = set()
    
    if not total_pages:
        return all_article_links
        
    for page_num in range(1, total_pages + 1):
        page_url = f"{base_url}?page={page_num}&view=24"
        print(f"Scraping page {page_num}/{total_pages}...")
        
        try:
            response = requests.get(page_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link_tag in soup.find_all('a', class_='article__title'):
                href = link_tag.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    all_article_links.add(full_url)
            
            time.sleep(1) # Be polite to the server

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch page {page_num}. Skipping. Error: {e}")
            continue
            
    return all_article_links

# --- Main script execution ---
if __name__ == "__main__":
    start_url = "https://altenew.com/blogs/paper-crafting-inspiration-and-tips"
    output_filename = "links.txt"
    
    # 1. Get the total number of pages
    num_pages = get_last_page_number(f"{start_url}?view=24")
    
    # 2. Scrape the links from all pages
    links = scrape_all_blog_links(start_url, num_pages)
    
    # 3. Write the results to the output file
    if links:
        print(f"\nWriting {len(links)} unique links to {output_filename}...")
        # Use 'with open' to automatically handle closing the file
        with open(output_filename, 'w', encoding='utf-8') as f:
            for link in sorted(list(links)):
                f.write(link + '\n') # Write each link on a new line
        
        print(f"✅ Successfully saved links to {output_filename}")
    else:
        print("No links were found to save.")
