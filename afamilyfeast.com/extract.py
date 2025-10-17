import requests
from bs4 import BeautifulSoup
import time


def quick_scrape_afamilyfeast():
    """Quick scraper for A Family Feast URLs only"""
    all_urls = []

    for page in range(1, 170):
        if page == 1:
            url = "https://www.afamilyfeast.com/blog/"
        else:
            url = f"https://www.afamilyfeast.com/blog/page/{page}/"

        print(f"Page {page}: {url}")

        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all recipe articles in the main content
            main_content = soup.find("main", class_="content")
            if main_content:
                articles = main_content.find_all("article", class_="post")
            else:
                articles = soup.find_all("article", class_="post")

            if not articles:
                print(f"  No articles found - stopping at page {page-1}")
                break

            page_urls = []
            for article in articles:
                title_link = article.find("h2", class_="entry-title").find("a")
                if title_link and title_link.get("href"):
                    page_urls.append(title_link["href"])

            all_urls.extend(page_urls)
            print(f"  Found {len(page_urls)} recipes")

            time.sleep(0.3)  # Brief delay

        except Exception as e:
            print(f"  Error: {e}")
            continue

    # Save URLs
    with open("afamilyfeast_recipe_urls.txt", "w") as f:
        for url in all_urls:
            f.write(url + "\n")

    print(f"\nTotal: {len(all_urls)} recipe URLs saved to afamilyfeast_recipe_urls.txt")
    return all_urls


# Run the quick version
if __name__ == "__main__":
    urls = quick_scrape_afamilyfeast()
