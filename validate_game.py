import os

def list_game_files():
    """Lists all game files in the ./games directory."""
    game_dir = "./games"
    if not os.path.exists(game_dir):
        print("❌ ERROR: 'games' directory does not exist.")
        return []

    game_files = [f for f in os.listdir(game_dir) if os.path.isfile(os.path.join(game_dir, f))]
    
    if not game_files:
        print("❌ ERROR: No game files found in the './games' directory.")
        return []

    return game_files


def validate_game_file(file_path):
    """Validates the format of a game CSV file."""
    
    if not os.path.exists(file_path):
        print(f"❌ ERROR: File '{file_path}' does not exist.")
        return False
    
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    if not lines:
        print(f"❌ ERROR: File '{file_path}' is empty.")
        return False

    # Check title format
    first_line = lines[0].strip()
    if first_line.lower().startswith("title="):
        title = first_line.split("=", 1)[1].strip().strip('"')
        print(f"✅ Title detected: {title}")
        game_lines = lines[1:]  # Skip title line
    else:
        print(f"⚠️ WARNING: No title detected. Using filename instead.")
        game_lines = lines

    game_map = {}
    valid_lines = set()

    for index, line in enumerate(game_lines, start=1):
        parts = [p.strip() for p in line.strip().split(",")]

        if not parts or len(parts) < 1:
            print(f"❌ ERROR: Line {index} is empty or improperly formatted.")
            return False

        # First element is the story text
        storyline = parts[0]
        choices = parts[1:]

        # Validate choice pairs
        if len(choices) % 2 != 0:
            print(f"❌ ERROR: Line {index} has an uneven number of choices. Choices must be in pairs.")
            return False

        # Validate choices mapping
        for i in range(1, len(choices), 2):
            choice_text = choices[i - 1]
            try:
                target_line = int(choices[i])
                valid_lines.add(target_line)
            except ValueError:
                print(f"❌ ERROR: Invalid mapping in line {index} ('{choice_text}' does not map to a valid number).")
                return False

        # Store story segment
        game_map[index] = (storyline, choices)

    # Validate that all mapped lines exist
    missing_lines = valid_lines - set(game_map.keys())
    if missing_lines:
        print(f"❌ ERROR: The following mapped lines do not exist: {sorted(missing_lines)}")
        return False

    print(f"✅ Validation passed for '{file_path}'. No errors detected!")
    return True


def main():
    """Lists games and asks user which to validate."""
    game_files = list_game_files()
    
    if not game_files:
        return

    print("\nAvailable games for validation:")
    for i, game in enumerate(game_files, start=1):
        print(f"{i}. {game}")
    print("A. Validate ALL games")
    print("X. Exit")

    choice = input("\nSelect a game to validate (or 'A' for all, 'X' to exit): ").strip().lower()

    if choice == "x":
        print("Exiting...")
        return
    elif choice == "a":
        print("\n🔍 Validating all games...")
        for game in game_files:
            print(f"\n🔎 Validating {game}...")
            validate_game_file(os.path.join("./games", game))
    else:
        try:
            game_index = int(choice) - 1
            if 0 <= game_index < len(game_files):
                game_path = os.path.join("./games", game_files[game_index])
                print(f"\n🔎 Validating {game_files[game_index]}...")
                validate_game_file(game_path)
            else:
                print("❌ ERROR: Invalid selection.")
        except ValueError:
            print("❌ ERROR: Invalid input. Please enter a number or 'A'/'X'.")

if __name__ == "__main__":
    main()

