#!/usr/bin/env python3
"""
Script to renumber 'index' fields in greek_words arrays to start from 0.

Traverses a folder and its subfolders, finds all .txt files with valid JSON,
and renumbers the index field in greek_words array members if they don't start with 0.
"""

import json
import os
import sys
from pathlib import Path


def process_file(filepath: Path) -> tuple[bool, str]:
    """
    Process a single .txt file.
    
    Returns:
        tuple: (was_modified, message)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"Error reading file: {e}"
    
    # Try to parse as JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False, "Not valid JSON"
    
    # Check if it has greek_words array
    if not isinstance(data, dict) or 'greek_words' not in data:
        return False, "No greek_words array found"
    
    greek_words = data['greek_words']
    
    if not isinstance(greek_words, list) or len(greek_words) == 0:
        return False, "greek_words is empty or not a list"
    
    # Check if first index is already 0
    first_item = greek_words[0]
    if not isinstance(first_item, dict) or 'index' not in first_item:
        return False, "greek_words items don't have 'index' field"
    
    original_start = first_item['index']  # Save BEFORE modifying!
    
    if original_start == 0:
        return False, "Already starts with 0"
    
    # Renumber all indices starting from 0
    for i, word in enumerate(greek_words):
        if isinstance(word, dict) and 'index' in word:
            word['index'] = i
    
    # Write back to file with proper formatting
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True, f"Renumbered {len(greek_words)} items (was starting at {original_start}, now starts at 0)"
    except Exception as e:
        return False, f"Error writing file: {e}"


def process_folder(folder_path: str) -> dict:
    """
    Process all .txt files in a folder and its subfolders.
    
    Returns:
        dict: Statistics about processed files
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        print(f"Error: Folder '{folder_path}' does not exist.")
        return {}
    
    stats = {
        'total_txt_files': 0,
        'valid_json_files': 0,
        'modified_files': 0,
        'skipped_files': 0,
        'error_files': 0,
        'modifications': []
    }
    
    # Find all .txt files recursively
    for txt_file in folder.rglob('*.txt'):
        stats['total_txt_files'] += 1
        
        was_modified, message = process_file(txt_file)
        
        if "Not valid JSON" not in message and "No greek_words" not in message:
            stats['valid_json_files'] += 1
        
        if was_modified:
            stats['modified_files'] += 1
            stats['modifications'].append({
                'file': str(txt_file.relative_to(folder)),
                'message': message
            })
            print(f"✓ MODIFIED: {txt_file.relative_to(folder)} - {message}")
        elif "Error" in message:
            stats['error_files'] += 1
            print(f"✗ ERROR: {txt_file.relative_to(folder)} - {message}")
        else:
            stats['skipped_files'] += 1
            # Uncomment below to see skipped files:
            # print(f"  skipped: {txt_file.relative_to(folder)} - {message}")
    
    return stats


def main():
    # Get folder path from command line argument or use current directory
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = input("Enter folder path (or press Enter for current directory): ").strip()
        if not folder_path:
            folder_path = "."
    
    print(f"\nScanning folder: {os.path.abspath(folder_path)}")
    print("=" * 60)
    
    stats = process_folder(folder_path)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total .txt files found:        {stats.get('total_txt_files', 0)}")
    print(f"Valid JSON files:              {stats.get('valid_json_files', 0)}")
    print(f"Files modified:                {stats.get('modified_files', 0)}")
    print(f"Files skipped (already 0):     {stats.get('skipped_files', 0)}")
    print(f"Files with errors:             {stats.get('error_files', 0)}")
    
    if stats.get('modifications'):
        print("\nModified files:")
        for mod in stats['modifications']:
            print(f"  - {mod['file']}: {mod['message']}")


if __name__ == "__main__":
    main()
