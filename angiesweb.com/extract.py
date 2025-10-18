import requests
from bs4 import BeautifulSoup
import time


def scrape_all_pages(start_url, article_selector, next_page_selector):
    """
    Scrapes all article links from a blog-style website until the last page.

    Args:
        start_url (str): The initial URL to start scraping from.
        article_selector (str): The CSS selector for the article title links.
        next_page_selector (str): The CSS selector for the 'Older Posts' or 'Next Page' link.

    Returns:
        list: A list of all unique article URLs found.
    """
    all_article_links = set()
    current_url = start_url
    page_num = 0

    headers = {"User-Agent": "My-Web-Scraper-Bot/1.0"}

    # This loop continues as long as a 'current_url' exists.
    # It will stop when it can't find a 'next_page_selector' on the last page.
    while current_url:
        page_num += 1
        print(f"--- Scraping Page {page_num}: {current_url} ---")

        try:
            response = requests.get(current_url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find all article links using the provided selector
            article_elements = soup.select(article_selector)

            page_links = {
                link.get("href") for link in article_elements if link.get("href")
            }
            print(f"Found {len(page_links)} new articles on this page.")
            all_article_links.update(page_links)

            # Find the link to the next page using the provided selector
            next_link_element = soup.select_one(next_page_selector)

            if next_link_element:
                current_url = next_link_element.get("href")
            else:
                print("\nNo more pages found. Reached the end.")
                current_url = None  # This will stop the while loop

            time.sleep(1)  # Be polite!

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            break

    return list(all_article_links)


# --- Main execution block ---
if __name__ == "__main__":
    # --- Example 1: Scraping angiesweb.com ---
    print("Scraping angiesweb.com...")
    angies_links = scrape_all_pages(
        start_url="https://angiesweb.com/",
        article_selector="article h1.entry-title a",
        next_page_selector="div.nav-previous a",
    )

    # --- Example 2: Scraping apartmentapothecary.co.uk ---
    # print("\n\nScraping apartmentapothecary.co.uk...")
    # apothecary_links = scrape_all_pages(
    #     start_url="https://apartmentapothecary.co.uk/",
    #     article_selector="article h2.entry-title a",
    #     next_page_selector="div.nav-previous a"
    # )

    # For this run, we'll just save the links from the first site.
    # You can uncomment the second example to run it instead.
    scraped_links = angies_links

    print("\n\n=== Scraping Complete ===")
    print(f"Found a total of {len(scraped_links)} unique article links.")

    file_name = "links.txt"
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            for link in sorted(scraped_links):  # Sorting the links for a clean output
                f.write(f"{link}\n")

        print(f"Successfully saved {len(scraped_links)} links to {file_name}")

    except IOError as e:
        print(f"Error writing to file {file_name}: {e}")
