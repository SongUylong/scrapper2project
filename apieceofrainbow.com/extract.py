import requests
from bs4 import BeautifulSoup
import time


def get_category_links(main_url):
    """
    Scrapes all category links from the main navigation menu of the website.
    """
    links = set()
    try:
        response = requests.get(main_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # The main navigation menu has the id 'menu-main-menu'
        # We find all links within list items that are of object type 'category'
        nav_menu = soup.find("ul", id="menu-main-menu")
        if nav_menu:
            for item in nav_menu.find_all("li", class_="menu-item-object-category"):
                link = item.find("a")
                if link and link.has_attr("href") and "/category/" in link["href"]:
                    links.add(link["href"])

        if not links:
            print(
                "Could not automatically find category links. Using the provided list."
            )
            # Fallback to the original list if categories are not found
            return [
                "https://www.apieceofrainbow.com/category/diy/",
                "https://www.apieceofrainbow.com/category/home-decor/",
                "https://www.apieceofrainbow.com/category/gardening-landscape/",
                "https://www.apieceofrainbow.com/category/christmas-decorations-gift-ideas/",
                "https://www.apieceofrainbow.com/category/arts-crafts/",
            ]

    except requests.exceptions.RequestException as e:
        print(f"Error fetching category links from {main_url}: {e}")
    return list(links)


def get_links_from_page(url):
    """
    Scrapes all blog post links from a given category page.
    """
    links = set()
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        for article in soup.find_all("article", class_="entry-card"):
            title = article.find("h6", class_="entry-title")
            if title:
                link = title.find("a")
                if link and link.has_attr("href"):
                    links.add(link["href"])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
    return links


def scrape_all_links(start_urls):
    """
    Scrapes all blog post links from the given start URLs, following pagination.
    """
    all_links = set()
    for url in start_urls:
        current_url = url
        page_num = 1
        while current_url:
            print(f"Scraping: {current_url}")
            links_on_page = get_links_from_page(current_url)
            if not links_on_page:
                print(
                    f"No links found on page {page_num} of {url}. Moving to next URL."
                )
                break

            all_links.update(links_on_page)

            try:
                response = requests.get(current_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                next_page_tag = soup.find("a", class_="next page-numbers")

                if next_page_tag and next_page_tag.has_attr("href"):
                    current_url = next_page_tag["href"]
                    page_num += 1
                    time.sleep(1)
                else:
                    current_url = None
            except requests.exceptions.RequestException as e:
                print(
                    f"Error occurred while trying to find next page from {current_url}: {e}"
                )
                current_url = None
    return all_links


if __name__ == "__main__":
    main_site_url = "https://www.apieceofrainbow.com/"

    print("Finding category links...")
    category_urls = get_category_links(main_site_url)

    if category_urls:
        print(f"Found {len(category_urls)} categories to scrape.")
        scraped_links = scrape_all_links(category_urls)

        with open("links.txt", "w") as f:
            for link in sorted(list(scraped_links)):
                f.write(link + "\n")

        print(f"\nFinished scraping. Found {len(scraped_links)} unique links.")
        print("All links have been saved to links.txt")
    else:
        print("Could not scrape any links.")
