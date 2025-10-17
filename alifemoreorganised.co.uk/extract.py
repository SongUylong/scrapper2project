import requests
from bs4 import BeautifulSoup
import time

def get_total_pages(session, base_url):
    """
    Finds the total number of pages by finding the 'Last page' link.
    """
    try:
        response = session.get(base_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        last_page_tag = soup.find('a', {'data-hook': 'pagination__last'})
        
        if last_page_tag and 'href' in last_page_tag.attrs:
            last_page_url = last_page_tag['href']
            # Extract the number from the end of the URL
            total_pages = int(last_page_url.split('/')[-1])
            return total_pages
        else:
            # If there's no pagination link, there's only one page
            return 1
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to {base_url}: {e}")
        return 1
    except (AttributeError, ValueError):
        print("Could not determine total pages. Defaulting to 1.")
        return 1


def scrape_page(url, session):
    """
    Scrapes the URLs for all posts on a single page.
    """
    urls_on_page = []
    try:
        response = session.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all the link tags directly
        link_tags = soup.select('div.item-link-wrapper a.O16KGI')

        for link_tag in link_tags:
            if link_tag and 'href' in link_tag.attrs:
                urls_on_page.append(link_tag['href'])
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {url}: {e}")

    return urls_on_page


def main():
    """
    Main function to orchestrate the scraping process.
    """
    BASE_URL = "https://www.alifemoreorganised.co.uk/blog"
    all_post_urls = []

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    print("Determining total number of pages...")
    total_pages = get_total_pages(session, BASE_URL)
    print(f"Found {total_pages} pages to scrape.")

    for page_num in range(1, total_pages + 1):
        if page_num == 1:
            current_url = BASE_URL
        else:
            current_url = f"{BASE_URL}/page/{page_num}"

        print(f"\nScraping page {page_num} of {total_pages}: {current_url}")
        
        page_urls = scrape_page(current_url, session)
        
        if page_urls:
            all_post_urls.extend(page_urls)
            print(f"-> Found {len(page_urls)} URLs.")
        else:
            print("-> No URLs found on this page, stopping.")
            break
        
        time.sleep(1) # Be polite to the server

    if all_post_urls:
        # ---- MODIFIED SECTION: Save only URLs to a .txt file ----
        output_file = 'blog_post_urls.txt'
        
        try:
            # Open the file in write mode ('w')
            with open(output_file, 'w', encoding='utf-8') as f:
                # Loop through each URL in the list
                for url in all_post_urls:
                    # Write the URL followed by a newline character
                    f.write(url + '\n')
            
            print("\n✅ Scraping complete!")
            print(f"Successfully scraped a total of {len(all_post_urls)} URLs.")
            print(f"Data saved to '{output_file}'.")
            
        except IOError as e:
            print(f"\n❌ Error writing to file: {e}")
            
    else:
        print("\n❌ Scraping finished, but no data was collected.")

if __name__ == "__main__":
    main()
