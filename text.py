import os

print("Current Working Directory:", os.getcwd())
file_path = "./games/lost_forest.csv"

if os.path.exists(file_path):
    print("✅ File exists! Python can detect it.")
else:
    print("❌ File does NOT exist according to Python.")

