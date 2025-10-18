import requests
from bs4 import BeautifulSoup
import time
from urllib.parse import urljoin

# Define headers to mimic a web browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def scrape_category_links(base_url):
    """
    Scrapes all recipe links from a category, navigating through all pages.

    Args:
        base_url (str): The starting URL for the category.

    Returns:
        list: A list of all unique recipe URLs found in the category.
    """
    current_url = base_url
    page_number = 1
    category_links = []

    while current_url:
        print(f"Scraping page {page_number} from category: {base_url}")
        try:
            response = requests.get(current_url, headers=HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Find all <a> tags inside <h2> tags with the class "entry-title"
            article_links = soup.select("h2.entry-title a")

            if not article_links and page_number == 1:
                print(" -> No article links found in this category.")
                break

            for link in article_links:
                href = link.get("href")
                if href:
                    full_url = urljoin(base_url, href)
                    category_links.append(full_url)

            # Find the "Next Page" link
            next_page_link = soup.select_one(".pagination-next a")
            if next_page_link and next_page_link.get("href"):
                current_url = next_page_link.get("href")
                page_number += 1
                time.sleep(1)  # Be polite to the server
            else:
                current_url = None  # No more pages

        except requests.exceptions.RequestException as e:
            print(f"An error occurred while scraping {current_url}: {e}")
            break

    return category_links


def save_links_to_txt(links, filename="recipe_links.txt"):
    """Saves a list of links to a text file, one link per line."""
    # Use a set to automatically remove duplicate links
    unique_links = sorted(list(set(links)))
    with open(filename, "w", encoding="utf-8") as f:
        for link in unique_links:
            f.write(link + "\n")
    print(f"\nSuccessfully saved {len(unique_links)} unique links to {filename}")


if __name__ == "__main__":
    category_urls = [
        "https://www.amummytoo.co.uk/category/festive-makes/",
        "https://www.amummytoo.co.uk/category/breakfast-food-and-drink/",
        "https://www.amummytoo.co.uk/category/valentines-day/",
        "https://www.amummytoo.co.uk/category/easter/",
        "https://www.amummytoo.co.uk/vegan-recipe-index/",
        "https://www.amummytoo.co.uk/vegetarian-recipe-index/",
        "https://www.amummytoo.co.uk/gluten-free-recipe-index/",
        "https://www.amummytoo.co.uk/category/halloween/",
    ]

    all_recipe_links = []
    for url in category_urls:
        print(f"\n{'='*20}\nScraping Category: {url}\n{'='*20}")
        links_from_category = scrape_category_links(url)
        if links_from_category:
            all_recipe_links.extend(links_from_category)
        time.sleep(2)  # Pause between categories

    if all_recipe_links:
        save_links_to_txt(all_recipe_links)

    print("\nAll categories scraped.")
