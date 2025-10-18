import re
import json
import os

# --- Configuration ---
INPUT_FILE = "acozy_not_cleaned.jsonl"
OUTPUT_FILE = "acozy_data_CLEANED.jsonl"

def format_image_tag(match):
    """
    This function is called for every <img> tag found.
    It extracts the src and returns the new formatted string.
    """
    tag_string = match.group(0) # The full <img> tag HTML
    
    # Prioritize lazy-loading sources, then the standard src
    src_match = re.search(r'(?:data-lazy-src|src)="([^"]+)"', tag_string)
    
    if src_match:
        url = src_match.group(1)
        # Exclude tiny spacer/data images
        if not url.startswith('data:image'):
            return f"[image: {url}]"
            
    # If no valid src is found, remove the tag entirely
    return ""

def clean_file(input_path, output_path):
    """
    Reads the input file, cleans each line, and writes to the output file.
    """
    print(f"Reading from: {input_path}")
    cleaned_lines = 0
    
    # Define the regex to find all <img> tags
    img_tag_regex = re.compile(r'<img[^>]+>')
    
    # --- NEW: Define regex to find all <iframe> tags ---
    # The re.DOTALL flag allows '.' to match newline characters, catching multi-line iframes
    iframe_tag_regex = re.compile(r'<iframe.*?</iframe>', re.DOTALL)

    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            try:
                data = json.loads(line)

                # Check if 'Text' field exists
                if 'Text' in data:
                    # 1. Process img tags first
                    processed_text = img_tag_regex.sub(format_image_tag, data['Text'])
                    
                    # --- NEW: 2. Remove iframe tags from the result ---
                    processed_text = iframe_tag_regex.sub('', processed_text)
                    
                    # Also clean the 'content' field in meta if it exists
                    if data.get('meta', {}).get('data_info', {}).get('content'):
                        content = data['meta']['data_info']['content']
                        content = img_tag_regex.sub(format_image_tag, content)
                        content = iframe_tag_regex.sub('', content) # Also remove iframes from here
                        data['meta']['data_info']['content'] = content

                    data['Text'] = processed_text
                    
                # Write the (potentially modified) data to the new file
                outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                cleaned_lines += 1

            except json.JSONDecodeError:
                print(f"Warning: Skipping a malformed line: {line.strip()}")
                continue
                
    print(f"\n✨ Done! Cleaned {cleaned_lines} articles.")
    print(f"Formatted data saved to: {output_path}")


if __name__ == "__main__":
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found. Please make sure it's in the same directory.")
    else:
        clean_file(INPUT_FILE, OUTPUT_FILE)