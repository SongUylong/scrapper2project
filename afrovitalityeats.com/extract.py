from bs4 import BeautifulSoup


def extract_all_article_links_robust(file_path):
    """
    Extract all article links using multiple methods for reliability
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()

        soup = BeautifulSoup(html_content, "html.parser")
        article_links = []

        # Method 1: Find all article elements and extract links
        articles = soup.find_all("article")

        for article in articles:
            # Try multiple ways to find the article link

            # Method A: Look for links in the title section that are not category links
            title_links = article.find_all("a", href=True)
            for link in title_links:
                href = link["href"]
                if "/category/" not in href and href not in article_links:
                    article_links.append(href)
                    break

            # Method B: Look for specific structure with gb-block-post-grid-title
            title_section = article.find("h4", class_="gb-block-post-grid-title")
            if title_section:
                links = title_section.find_all("a", href=True)
                for link in links:
                    href = link["href"]
                    if "/category/" not in href and href not in article_links:
                        article_links.append(href)
                        break

        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in article_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)

        return unique_links

    except Exception as e:
        print(f"Error: {e}")
        return []


def write_links_to_file(links, output_file="all_article_links.txt"):
    """
    Write extracted links to a file
    """
    try:
        with open(output_file, "w", encoding="utf-8") as file:
            for link in links:
                file.write(link + "\n")
        print(f"Successfully wrote {len(links)} article links to {output_file}")
    except Exception as e:
        print(f"Error writing to file: {e}")


# Main execution
if __name__ == "__main__":
    file_path = "main.html"  # Your HTML file path
    output_file = "all_article_links.txt"

    print("Extracting article links...")
    article_links = extract_all_article_links_robust(file_path)

    if article_links:
        print(f"\nFound {len(article_links)} unique article links:")
        print("-" * 50)
        for i, link in enumerate(article_links, 1):
            print(f"{i:2d}. {link}")
        print("-" * 50)

        # Write to file
        write_links_to_file(article_links, output_file)

        # Show sample of what was extracted
        print(f"\nSample links extracted:")
        for i in range(min(3, len(article_links))):
            print(f"  • {article_links[i]}")

    else:
        print("No article links found in the file.")
