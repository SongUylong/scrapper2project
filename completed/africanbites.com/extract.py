import requests
from bs4 import BeautifulSoup
import time
import os
import concurrent.futures
from urllib.parse import urljoin
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FastScraper:
    def __init__(self, max_workers=5):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.max_workers = max_workers

    def scrape_page(self, url):
        """Scrape a single page and return links"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            articles = soup.find_all("article", class_="entry")

            links = []
            for article in articles:
                title_element = article.find("h2", class_="entry-title")
                if title_element:
                    title_link = title_element.find("a")
                    if title_link and title_link.get("href"):
                        links.append(title_link["href"])

            return links, soup.find("a", class_="next") is not None

        except Exception as e:
            logger.warning(f"Error scraping {url}: {e}")
            return [], False

    def generate_page_urls(self, category_url, max_pages=10):
        """Generate all page URLs for a category"""
        urls = [category_url.rstrip("/")]

        # Generate subsequent page URLs
        for page_num in range(2, max_pages + 1):
            urls.append(f"{category_url.rstrip('/')}/page/{page_num}/")

        return urls

    def scrape_category_parallel(self, category_url, output_file, max_pages=10):
        """Scrape a category using parallel requests"""
        urls = self.generate_page_urls(category_url, max_pages)
        all_links = []

        # Scrape pages in parallel
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_url = {
                executor.submit(self.scrape_page, url): url for url in urls
            }

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    links, has_next = future.result()
                    all_links.extend(links)
                    logger.info(f"Scraped {url}: found {len(links)} links")

                except Exception as e:
                    logger.warning(f"Failed to scrape {url}: {e}")

        # Write all links for this category
        with open(output_file, "a", encoding="utf-8") as f:
            for link in all_links:
                f.write(f"{link}\n")

        return len(all_links)

    def scrape_category_optimized(self, category_url, output_file, max_pages=10):
        """Optimized sequential scraping with better page detection"""
        page_num = 1
        total_links = 0

        while page_num <= max_pages:
            if page_num == 1:
                url = category_url.rstrip("/")
            else:
                url = f"{category_url.rstrip('/')}/page/{page_num}/"

            logger.info(f"Scraping page {page_num}: {url}")

            links, has_next = self.scrape_page(url)

            if not links and page_num > 1:
                logger.info("No more articles found. Moving to next category.")
                break

            # Write links immediately
            with open(output_file, "a", encoding="utf-8") as f:
                for link in links:
                    f.write(f"{link}\n")

            total_links += len(links)
            logger.info(f"Page {page_num}: Found {len(links)} links")

            if not has_next:
                logger.info(f"No more pages. Total pages: {page_num}")
                break

            page_num += 1

            # Reduced delay for sequential scraping
            if page_num <= max_pages:
                time.sleep(0.5)  # Reduced from 2 seconds

        return total_links


def read_categories_from_file(filename):
    """Read categories from file and return as list"""
    categories = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    categories.append(line)
        return categories
    except FileNotFoundError:
        logger.error(f"Categories file '{filename}' not found.")
        return []
    except Exception as e:
        logger.error(f"Error reading categories file: {e}")
        return []


def scrape_all_categories_parallel():
    """Main function using parallel execution"""
    categories_file = "categories.txt"
    output_file = "all_articles_links.txt"

    categories = read_categories_from_file(categories_file)
    if not categories:
        logger.error("No categories found to scrape.")
        return

    logger.info(f"Found {len(categories)} categories to scrape")

    # Clear output file
    if os.path.exists(output_file):
        os.remove(output_file)

    scraper = FastScraper(
        max_workers=8
    )  # Increase workers for parallel category scraping

    # Scrape categories in parallel
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=3
    ) as executor:  # Limit concurrent categories
        future_to_category = {
            executor.submit(
                scraper.scrape_category_parallel, category, output_file
            ): category
            for category in categories
        }

        for future in concurrent.futures.as_completed(future_to_category):
            category = future_to_category[future]
            try:
                links_count = future.result()
                logger.info(f"Completed {category}: {links_count} links")
            except Exception as e:
                logger.error(f"Failed to scrape category {category}: {e}")

    generate_final_summary(output_file)


def scrape_all_categories_fast_sequential():
    """Faster sequential version if parallel causes issues"""
    categories_file = "categories.txt"
    output_file = "all_articles_links.txt"

    categories = read_categories_from_file(categories_file)
    if not categories:
        logger.error("No categories found to scrape.")
        return

    logger.info(f"Found {len(categories)} categories to scrape")

    if os.path.exists(output_file):
        os.remove(output_file)

    scraper = FastScraper()
    total_links = 0

    for i, category_url in enumerate(categories, 1):
        logger.info(f"[{i}/{len(categories)}] Scraping category: {category_url}")

        links_count = scraper.scrape_category_optimized(category_url, output_file)
        total_links += links_count
        logger.info(f"✓ Category completed: {links_count} links")

        # Reduced delay between categories
        if i < len(categories):
            time.sleep(1)  # Reduced from 3 seconds

    generate_final_summary(output_file)


def generate_final_summary(output_file):
    """Generate final summary report"""
    logger.info("=" * 50)
    logger.info("SCRAPING COMPLETED!")
    logger.info("=" * 50)

    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            all_links = f.readlines()
            unique_links = set(all_links)

        logger.info(f"Total links collected: {len(all_links)}")
        logger.info(f"Unique links: {len(unique_links)}")
        logger.info(f"Links saved to: {output_file}")

        # Save unique links
        unique_file = "unique_articles_links.txt"
        with open(unique_file, "w", encoding="utf-8") as f:
            f.writelines(sorted(unique_links))
        logger.info(f"Unique links also saved to: {unique_file}")
    else:
        logger.warning("No links were collected.")


if __name__ == "__main__":
    # Choose your preferred method:

    # Method 1: Maximum speed (parallel processing)
    # WARNING: This may get you blocked if the server has rate limiting
    scrape_all_categories_parallel()

    # Method 2: Balanced speed (optimized sequential)
    # More respectful to the server but still much faster than original
    # scrape_all_categories_fast_sequential()
