import requests
import hashlib
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class DailyLifeScraper:
    def __init__(self, max_workers=5):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            }
        )
        self.lock = threading.Lock()
        self.max_workers = max_workers

    def generate_id(self, url):
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def anonymize_text(self, text):
        text = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "x@x.xx", text
        )
        text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "xxx-xxx-xxxx", text)
        text = re.sub(r"\bKristi\b", "x", text, flags=re.IGNORECASE)
        text = re.sub(r"\bMatt\b", "x", text, flags=re.IGNORECASE)
        text = re.sub(r"\bLinauer\b", "x", text, flags=re.IGNORECASE)
        return text

    def clean_text(self, text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n+", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"^[ \t]+", "", text, flags=re.MULTILINE)
        text = re.sub(r"[^\x00-\x7F]+", "", text)
        text = " ".join(text.split())
        return text.strip()

    def should_remove_element(self, element):
        element_classes = element.get("class", [])
        element_id = element.get("id", "")
        classes_str = (
            " ".join(element_classes)
            if isinstance(element_classes, list)
            else str(element_classes)
        )

        unwanted_patterns = [
            "adthrive",
            "ad-container",
            "sabox",
            "ml-form-embedContainer",
            "comments-area",
            "comments",
            "subscribe",
            "newsletter",
            "author-bio",
        ]

        for pattern in unwanted_patterns:
            if (
                pattern in classes_str.lower()
                or pattern in str(element_id).lower()
                or pattern in element.name.lower()
            ):
                return True
        return False

    def extract_content_with_images(self, soup):
        content_element = soup.find("div", class_="entry-content")
        if not content_element:
            return "", []

        author_bio = content_element.find("div", class_="sabox-authors")
        if author_bio:
            author_bio.decompose()

        for unwanted in content_element.find_all(
            ["script", "style", "div", "iframe", "nav", "footer", "aside", "form"]
        ):
            if self.should_remove_element(unwanted):
                unwanted.decompose()

        content_parts = []
        images = []

        for element in content_element.find_all(recursive=True):
            if element.name == "img":
                img_src = element.get("src") or element.get("data-lazy-src")
                if img_src and img_src.startswith(("http://", "https://")):
                    img_alt = element.get("alt", "")
                    img_marker = f"[image: {img_src}]"
                    content_parts.append(img_marker)
                    images.append({"url": img_src, "alt": img_alt})

            elif element.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6"]:
                text = element.get_text().strip()
                if text and not any(
                    x in text.lower()
                    for x in [
                        "advertisement",
                        "comment",
                        "subscribe",
                        "never miss",
                        "email inbox",
                        "kristi@addicted2decorating.com",
                        "leave a reply",
                        "post comment",
                        "required fields are marked",
                    ]
                ):
                    cleaned_text = self.clean_text(text)
                    if cleaned_text and len(cleaned_text) > 10:
                        content_parts.append(cleaned_text)

        return "\n".join(content_parts), images

    def determine_subdomain(self, title, content):
        text_to_analyze = f"{title} {content}".lower()
        subdomain_keywords = {
            "home_care": [
                "clean",
                "cleaning",
                "storage",
                "organize",
                "stain",
                "home care",
                "household",
                "kitchen",
                "condo",
                "design",
                "countertop",
                "cabinet",
            ],
            "diy": [
                "diy",
                "paint",
                "remodel",
                "makeover",
                "project",
                "do it yourself",
                "butcher block",
                "countertop",
                "backsplash",
                "tile",
            ],
        }
        scores = {domain: 0 for domain in subdomain_keywords}
        for domain, keywords in subdomain_keywords.items():
            for keyword in keywords:
                if keyword in text_to_analyze:
                    scores[domain] += 1
        return max(scores.items(), key=lambda x: x[1])[0]

    def scrape_article(self, url):
        try:
            response = self.session.get(url, timeout=15)  # Reduced timeout
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            title_element = soup.find("h1", class_="entry-title")
            title = (
                self.clean_text(title_element.get_text().strip())
                if title_element
                else "Untitled Article"
            )

            content, images = self.extract_content_with_images(soup)
            cleaned_content = self.clean_text(content)
            anonymized_content = self.anonymize_text(cleaned_content)

            if len(anonymized_content) < 200:
                return None

            categories = []
            category_elements = soup.select(".entry-taxonomies .category-links a")
            for cat in category_elements:
                cat_text = self.clean_text(cat.get_text())
                if cat_text:
                    categories.append(cat_text)

            subdomain = self.determine_subdomain(title, anonymized_content)

            final_text = f"{title}\n{anonymized_content}"

            article_data = {
                "ID": self.generate_id(url),
                "text": final_text,
                "meta": {
                    "data_info": {
                        "lang": "en",
                        "url": url,
                        "source": urlparse(url).netloc,
                        "type": "Article",
                        "processing_date": datetime.now().strftime("%Y-%m-%d"),
                        "delivery_version": "V1.0",
                        "title": title,
                        "content": anonymized_content,
                        "content_info": {
                            "domain": "daily_life",
                            "subdomain": subdomain,
                        },
                    }
                },
            }

            return article_data

        except Exception as e:
            return None


def read_urls_from_file(filename):
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found")
        return []

    with open(filename, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(urls)} URLs from {filename}")
    return urls


def scrape_single_url(args):
    """Helper function for threading"""
    scraper, url, index, total = args
    result = scraper.scrape_article(url)
    return url, result, index, total


def main():
    # Read URLs
    url_file = "blog_urls.txt"
    urls = read_urls_from_file(url_file)

    if not urls:
        print("No URLs to process.")
        return

    # Initialize scraper with more workers for faster processing
    scraper = DailyLifeScraper(max_workers=10)
    output_file = "scraped_articles.jsonl"

    successful_count = 0
    failed_count = 0

    print(f"Starting multi-threaded scraping of {len(urls)} URLs...")
    print("=" * 60)

    start_time = time.time()

    with open(output_file, "w", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=scraper.max_workers) as executor:
            # Prepare tasks
            tasks = [(scraper, url, i + 1, len(urls)) for i, url in enumerate(urls)]

            # Submit all tasks
            future_to_url = {
                executor.submit(scrape_single_url, task): task for task in tasks
            }

            # Process completed tasks
            for future in as_completed(future_to_url):
                url, result, index, total = future_to_url[future]

                try:
                    url, article_data, index, total = future.result()

                    if article_data:
                        with scraper.lock:  # Thread-safe file writing
                            f.write(json.dumps(article_data, ensure_ascii=False) + "\n")
                        successful_count += 1
                        print(f"✓ [{index}/{total}] Success: {url}")
                    else:
                        failed_count += 1
                        print(f"✗ [{index}/{total}] Failed: {url}")

                except Exception as e:
                    failed_count += 1
                    print(f"✗ [{index}/{total}] Error: {url} - {str(e)}")

    end_time = time.time()
    total_time = end_time - start_time

    # Print final summary
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED!")
    print("=" * 60)
    print(f"Total URLs processed: {len(urls)}")
    print(f"Successfully scraped: {successful_count}")
    print(f"Failed: {failed_count}")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Average time per URL: {total_time/len(urls):.2f} seconds")
    print(f"Output file: {output_file}")

    if successful_count > 0:
        print(f"Success rate: {(successful_count/len(urls))*100:.1f}%")


if __name__ == "__main__":
    main()
