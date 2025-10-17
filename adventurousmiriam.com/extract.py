import requests
from bs4 import BeautifulSoup
import time


def get_blog_urls_simple():
    """Simple function to get all blog URLs"""
    urls = []

    for page in range(1, 73):  # Pages 1 to 72
        if page == 1:
            url = "https://adventurousmiriam.com/blog/"
        else:
            url = f"https://adventurousmiriam.com/blog/page/{page}/"

        print(f"Checking page {page}...")

        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all article links
            articles = soup.find_all("article", class_="kt-blocks-post-grid-item")

            if not articles:
                print(f"No more articles found. Stopped at page {page-1}")
                break

            for article in articles:
                link = article.find("h2", class_="entry-title").find("a")
                if link and link.get("href"):
                    urls.append(link["href"])

            print(f"Found {len(articles)} articles on page {page}")
            time.sleep(0.5)  # Be nice to the server

        except Exception as e:
            print(f"Error on page {page}: {e}")
            break

    # Save URLs to file
    with open("blog_urls.txt", "w") as f:
        for url in urls:
            f.write(url + "\n")

    print(f"\nTotal URLs found: {len(urls)}")
    return urls


# Run the simple version
if __name__ == "__main__":
    urls = get_blog_urls_simple()
