from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin

# --- Configuration ---
# Set the base URL of the website.
BASE_URL = "https://www.angi.com"
# Set the input filename for the HTML content.
INPUT_HTML_FILE = "main1.html"
# Set the output filename for the extracted links.
OUTPUT_TXT_FILE = "links1.txt"
# --- End of Configuration ---


def scrape_full_links(input_file, output_file, base_url):
    """
    Parses an HTML file to find all article links, converts them to full URLs,
    and saves them to a text file.

    Args:
        input_file (str): The path to the input HTML file.
        output_file (str): The path to the output text file.
        base_url (str): The base URL to prepend to relative paths.
    """
    if not os.path.exists(input_file):
        print(f"Error: The file '{input_file}' was not found.")
        return

    with open(output_file, "w") as f_out:
        with open(input_file, "r", encoding="utf-8") as f_in:
            soup = BeautifulSoup(f_in, "html.parser")

            article_links = soup.select(
                "a.ContentCard_title-content-size-small__6HRGQ.ContentCard_anchor__w9Of8"
            )

            if not article_links:
                print("No article links found with the specified selector.")
                return

            print(
                f"Found {len(article_links)} links. Writing full URLs to '{output_file}'..."
            )

            for link in article_links:
                relative_path = link.get("href")
                if relative_path:
                    # Combine the base URL with the relative path to create a full link.
                    full_url = urljoin(base_url, relative_path)
                    # Write the full URL to the output file.
                    f_out.write(full_url + "\n")

    print("Scraping complete. All full links have been saved.")


# --- Main execution block ---
if __name__ == "__main__":
    scrape_full_links(INPUT_HTML_FILE, OUTPUT_TXT_FILE, BASE_URL)
