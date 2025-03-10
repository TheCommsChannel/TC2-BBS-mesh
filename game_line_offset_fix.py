# This will fix a gamefile that was written with a title="Title" on line 1, but was not offset 
# to account for that. If title="Title" is used on line 1, that line should then be treated
# as line 0. The gamefile processor assumes line 1 is the first line that doesn't start with title=
# This script will subtract one from every line number mapping in the gamefile. 

# Alternatively, you could add a "dummy line" to the second storyline shifting the rest of 
# the file down by one line. 

import re
import os

def list_game_files(directory):
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def adjust_numbers_in_file(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    updated_lines = []
    for line in lines:
        # Preserve title line
        if line.startswith("title="):
            updated_lines.append(line)
            continue
        
        # Find numbers and subtract 1 from each
        def adjust_number(match):
            return f", {match.group(1)}, {int(match.group(2)) - 1}"
        
        updated_line = re.sub(r",\s*([^,]+)\s*,\s*(\d+)", adjust_number, line)
        updated_lines.append(updated_line)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(updated_lines)

def main():
    games_dir = "./games"
    game_files = list_game_files(games_dir)
    
    if not game_files:
        print("No files found in the ./games directory.")
        return
    
    print("Select a file to process:")
    for idx, filename in enumerate(game_files, start=1):
        print(f"{idx}: {filename}")
    
    choice = int(input("Enter the number of the file: ")) - 1
    if choice < 0 or choice >= len(game_files):
        print("Invalid selection.")
        return
    
    input_filename = game_files[choice]
    input_filepath = os.path.join(games_dir, input_filename)
    output_filename = f"{os.path.splitext(input_filename)[0]}-linefix{os.path.splitext(input_filename)[1]}"
    output_filepath = os.path.join(games_dir, output_filename)
    
    adjust_numbers_in_file(input_filepath, output_filepath)
    print(f"Processed file saved as: {output_filename}")

if __name__ == "__main__":
    main()
