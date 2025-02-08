import os
import re

def process_file(input_filename, output_filename):
    """Reads a file line by line, removing commas from lines that do not contain a number."""
    
    if not os.path.exists(input_filename):
        print(f"❌ Error: File '{input_filename}' not found. Please check the path.")
        return  # Exit the function

    with open(input_filename, 'r', encoding='utf-8') as infile, \
         open(output_filename, 'w', encoding='utf-8') as outfile:

        for line in infile:
            if re.search(r'\d', line):  # Checks if line contains any digit (0-9)
                outfile.write(line)  # Keep the line as is
            else:
                cleaned_line = line.replace(',', '')  # Remove commas
                outfile.write(cleaned_line)  # Write the cleaned line

    print(f"✅ Processing complete! Cleaned file saved as '{output_filename}'.")

# Example usage
input_file = "games/forgotten_ruins_gpt.csv"
output_file = "games/cleaned_forgotten_ruins_gpt.csv"

process_file(input_file, output_file)

