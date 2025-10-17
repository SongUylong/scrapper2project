from bs4 import BeautifulSoup
import os

# Define the input and output filenames
input_html_file = 'main.html'
output_txt_file = 'links.txt'

# Check if the input file exists
if not os.path.exists(input_html_file):
    print(f"Error: The file '{input_html_file}' was not found in this directory.")
else:
    try:
        # --- Step 1: Read the HTML file ---
        with open(input_html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # --- Step 2: Parse the HTML with Beautiful Soup ---
        soup = BeautifulSoup(html_content, 'html.parser')

        # --- Step 3: Find all article containers ---
        # The provided HTML uses <article> tags with the class 'fusion-post-grid'
        articles = soup.find_all('article', class_='fusion-post-grid')
        
        extracted_links = []
        for article in articles:
            # Find the <h2> tag with the class 'entry-title' which holds the main link
            title_element = article.find('h2', class_='entry-title')
            if title_element:
                link_element = title_element.find('a')
                # Check if the <a> tag exists and has an 'href' attribute
                if link_element and 'href' in link_element.attrs:
                    extracted_links.append(link_element['href'])

        # --- Step 4: Write the extracted links to a file ---
        with open(output_txt_file, 'w', encoding='utf-8') as f:
            for link in extracted_links:
                f.write(link + '\n') # Write each link on a new line
        
        print(f"✅ Success! Scraped {len(extracted_links)} links and saved them to '{output_txt_file}'")

    except Exception as e:
        print(f"❌ An error occurred: {e}")
