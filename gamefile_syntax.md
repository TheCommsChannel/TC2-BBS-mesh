# 📜 How to Format Game CSV Files

This guide explains how to structure game files for the **text-based game system** using **CSV format**.

---

## 📌 **Basic Structure**
Each line in the CSV file represents a **story segment** with:
- **Storyline text** (always first column)
- **Choices** (paired as `Choice Text, Target Line`)
- If no choices exist, it signals **GAME OVER**

### **Example Format:**
```csv
What is your first choice?, East, 2, West, 3, North, 4, South, 5
You chose East. A dense forest appears., Run forward, 6, Look around, 7
You chose West. A river blocks your path., Try to swim, 8, Walk along the bank, 9
You chose North. The path is blocked by rocks.
You chose South. A cave entrance looms ahead., Enter the cave, 10, Turn back, 11
You went East and chose to run. The ground gives way and you fall. GAME OVER.
You went East and looked around. You see a hidden path., Follow it, 12, Stay put, 13
```

---

## 📌 **Title Handling**
The **first line** of the file may contain a title in the format:
```csv
title="The Mysterious Forest"
```
- If present, the game uses this as the **title**.
- If absent, the **filename** is used as the title.
- The second line will then be the **first story segment**.

---

## 📌 **Rules for Formatting**
✅ **Each row starts with story text**
✅ **Choices appear as pairs** (`Choice Text, Target Line`)
✅ **Target Line must reference an existing line number**
✅ **A line without choices = GAME OVER**
✅ **Title (optional) must be in the first line as `title="Game Name"`**
✅ **File should be saved as `.csv` with UTF-8 encoding**

---

## 📌 **Understanding the Flow**
1️⃣ The game **starts at line 1**.
2️⃣ The user selects a **numbered choice**.
3️⃣ The game jumps to the **corresponding line number**.
4️⃣ The game continues until:
   - **No choices remain (GAME OVER)**
   - **The player exits** (`X` command).

---

## 📌 **Edge Cases & Notes**
⚠ **If an invalid line number is referenced**, the game may crash.
⚠ **A story segment must always be in column 1**, even if no choices follow.
⚠ **Extra spaces around text are automatically trimmed.**

---

## 📌 **Final Notes**
By following this format, you can create **interactive, branching text adventures** without modifying code! 🎮🚀

