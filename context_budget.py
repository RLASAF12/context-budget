#!/usr/bin/env python3

import argparse
import os
import sys
import tiktoken
import json
from collections import defaultdict
import re

# --- Constants ---
ENCODING_NAME = "cl100k_base"
CLAUDE_MAX_CONTEXT = 200000
DEFAULT_BUDGET = 50000
CLAUDE_MD_FILENAME = "CLAUDE.md"

# ANSI Color Codes
COLOR_RESET = "\033[0m"
COLOR_RED = "\033[91m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_MAGENTA = "\033[95m"
COLOR_BOLD = "\033[1m"

# Directories and file extensions to skip
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".vscode",
    ".idea",
    "build",
    "dist",
    "target",
    "out",
    "logs",
    "tmp",
}
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pdf", ".mp3", ".mp4", ".avi", ".mov",
    ".flac", ".ogg", ".webp", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".svgz",
    ".db", ".sqlite", ".sqlite3", ".bak", ".log", ".lock", ".swp", ".swo",
}

# --- Global Encoder Instance ---
_encoder = None

def get_encoder():
    """Returns the tiktoken encoder, caching it for performance."""
    global _encoder
    if _encoder is None:
        try:
            _encoder = tiktoken.get_encoding(ENCODING_NAME)
        except Exception as e:
            print(f"{COLOR_RED}Error loading tiktoken encoding '{ENCODING_NAME}': {e}{COLOR_RESET}", file=sys.stderr)
            print(f"{COLOR_RED}Please ensure 'tiktoken' is installed and '{ENCODING_NAME}' is a valid encoding.{COLOR_RESET}", file=sys.stderr)
            sys.exit(1)
    return _encoder

# --- Helper Functions ---

def is_binary(filepath):
    """
    Checks if a file is likely binary by attempting to read a small chunk
    and looking for null bytes or decoding errors.
    """
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024) # Read first 1KB
            if b'\0' in chunk: # Presence of null bytes often indicates binary
                return True
            # Try decoding as UTF-8; if it fails, it's likely not a text file
            chunk.decode('utf-8')
            return False
    except UnicodeDecodeError:
        return True
    except Exception: # Handle other potential errors like permission denied
        return True # Treat as binary if we can't read or decode

def count_tokens(filepath):
    """Counts tokens in a file using the specified tiktoken encoding."""
    encoder = get_encoder()
    try:
        if is_binary(filepath):
            return 0, True # Return 0 tokens and mark as binary
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            tokens = encoder.encode(content)
            return len(tokens), False
    except UnicodeDecodeError:
        # This can happen if is_binary() heuristic wasn't perfect, or file is mixed
        return 0, True
    except IOError as e:
        # print(f"{COLOR_YELLOW}Warning: Could not read '{filepath}' ({e}). Skipping.{COLOR_RESET}", file=sys.stderr)
        return 0, False # Treat as 0 tokens, not necessarily binary
    except Exception as e:
        # print(f"{COLOR_YELLOW}Warning: An unexpected error occurred while processing '{filepath}': {e}. Skipping.{COLOR_RESET}", file=sys.stderr)
        return 0, False

def should_skip(path):
    """Checks if a path (file or directory) should be skipped."""
    basename = os.path.basename(path)
    if basename in SKIP_DIRS:
        return True
    
    # Check if it's a directory and in SKIP_DIRS
    if os.path.isdir(path) and basename in SKIP_DIRS:
        return True

    # Check file extensions
    if os.path.isfile(path):
        _, ext = os.path.splitext(basename)
        if ext.lower() in SKIP_EXTENSIONS:
            return True
    
    return False

def colorize(text, color):
    """Applies ANSI color codes to text."""
    if sys.stdout.isatty():
        return f"{color}{text}{COLOR_RESET}"
    return text

def get_color_for_tokens(token_count, budget):
    """Returns a color based on token count relative to budget."""
    if token_count > budget:
        return COLOR_RED
    elif token_count > budget * 0.75:
        return COLOR_YELLOW
    else:
        return COLOR_GREEN

def format_token_output(token_count, budget, total_context_window=CLAUDE_MAX_CONTEXT):
    """Formats token count with color and percentage."""
    color = get_color_for_tokens(token_count, budget)
    percentage_budget = (token_count / budget) * 100 if budget > 0 else 0
    percentage_window = (token_count / total_context_window) * 100
    
    budget_str = f"({percentage_budget:.1f}% of budget)" if budget > 0 else ""
    window_str = f"({percentage_window:.1f}% of 200K window)"
    
    return colorize(f"{token_count:8d} tokens {budget_str} {window_str}", color)

# --- Command Implementations ---

def scan_command(args):
    """Recursively lists all files sorted by token count."""
    target_path = os.path.abspath(args.path)
    
    if not os.path.exists(target_path):
        print(colorize(f"Error: Path '{target_path}' does not exist.", COLOR_RED), file=sys.stderr)
        sys.exit(1)
    
    print(f"Scanning '{target_path}' for tokens...")
    
    file_tokens = []
    total_tokens = 0
    skipped_files = 0
    skipped_dirs = set()

    for root, dirs, files in os.walk(target_path):
        # Modify dirs in-place to skip unwanted directories
        dirs[:] = [d for d in dirs if not should_skip(os.path.join(root, d))]
        for d in list(dirs): # Iterate over a copy to allow modification
            if should_skip(os.path.join(root, d)):
                skipped_dirs.add(os.path.join(root, d))
                dirs.remove(d)

        for filename in files:
            filepath = os.path.join(root, filename)
            if should_skip(filepath):
                skipped_files += 1
                continue
            
            tokens, is_bin = count_tokens(filepath)
            if is_bin:
                skipped_files += 1
                continue

            file_tokens.append({'path': filepath, 'tokens': tokens})
            total_tokens += tokens

    file_tokens.sort(key=lambda x: x['tokens'], reverse=True)

    if args.format == 'json':
        json_output = {
            "scanned_path": target_path,
            "total_tokens": total_tokens,
            "total_context_window": CLAUDE_MAX_CONTEXT,
            "percentage_of_window": (total_tokens / CLAUDE_MAX_CONTEXT) * 100,
            "budget": args.budget,
            "files": file_tokens,
            "skipped_files_count": skipped_files,
            "skipped_directories_count": len(skipped_dirs),
        }
        print(json.dumps(json_output, indent=2))
    else:
        print(colorize(f"\n--- Token Scan Results for '{target_path}' ---", COLOR_BLUE))
        print(colorize(f"Budget: {args.budget} tokens", COLOR_CYAN))
        print(colorize(f"Claude Max Context: {CLAUDE_MAX_CONTEXT} tokens", COLOR_CYAN))
        print("-" * 80)

        for item in file_tokens:
            path = os.path.relpath(item['path'], target_path)
            print(f"{format_token_output(item['tokens'], args.budget)} {path}")
        
        print("-" * 80)
        print(f"Total files scanned: {len(file_tokens)}")
        print(f"Files/Binary/Skipped: {skipped_files}")
        print(f"Directories skipped: {len(skipped_dirs)}")
        print(colorize(f"Overall Total: {format_token_output(total_tokens, args.budget, CLAUDE_MAX_CONTEXT)}", COLOR_BOLD))
        print(colorize(f"Remaining budget: {args.budget - total_tokens} tokens", get_color_for_tokens(total_tokens, args.budget)))
        print("-" * 80)


def check_command(args):
    """Sums tokens for specific files and compares to budget."""
    file_details = []
    total_tokens = 0
    
    for filepath in args.files:
        abs_filepath = os.path.abspath(filepath)
        if not os.path.exists(abs_filepath):
            print(colorize(f"Warning: File '{filepath}' not found. Skipping.", COLOR_YELLOW), file=sys.stderr)
            continue
        
        tokens, is_bin = count_tokens(abs_filepath)
        if is_bin:
            print(colorize(f"Warning: File '{filepath}' appears to be binary. Skipping token count.", COLOR_YELLOW), file=sys.stderr)
            tokens = 0 # Explicitly set to 0 for binary files
        
        file_details.append({'path': filepath, 'tokens': tokens})
        total_tokens += tokens

    if args.format == 'json':
        json_output = {
            "total_tokens": total_tokens,
            "total_context_window": CLAUDE_MAX_CONTEXT,
            "percentage_of_window": (total_tokens / CLAUDE_MAX_CONTEXT) * 100,
            "budget": args.budget,
            "files": file_details,
        }
        print(json.dumps(json_output, indent=2))
    else:
        print(colorize(f"\n--- Token Check Results ---", COLOR_BLUE))
        print(colorize(f"Budget: {args.budget} tokens", COLOR_CYAN))
        print(colorize(f"Claude Max Context: {CLAUDE_MAX_CONTEXT} tokens", COLOR_CYAN))
        print("-" * 80)

        for item in file_details:
            print(f"{format_token_output(item['tokens'], args.budget)} {item['path']}")
        
        print("-" * 80)
        print(colorize(f"Overall Total: {format_token_output(total_tokens, args.budget, CLAUDE_MAX_CONTEXT)}", COLOR_BOLD))
        print(colorize(f"Remaining budget: {args.budget - total_tokens} tokens", get_color_for_tokens(total_tokens, args.budget)))
        print("-" * 80)


def tier_command(args):
    """Reads CLAUDE.md, identifies Tier 1/2/3 file mentions and their costs."""
    target_path = os.path.abspath(args.path)
    claude_md_path = os.path.join(target_path, CLAUDE_MD_FILENAME)

    if not os.path.exists(claude_md_path):
        print(colorize(f"Error: '{CLAUDE_MD_FILENAME}' not found in '{target_path}'.", COLOR_RED), file=sys.stderr)
        sys.exit(1)

    print(f"Reading '{claude_md_path}' for tier definitions...")

    tier_data = defaultdict(list)
    tier_totals = defaultdict(int)
    overall_total_tokens = 0
    
    tier_regex = re.compile(r"^(Tier\s[1-3]):\s*(.*)$", re.IGNORECASE)
    # Also match backtick-quoted paths mentioned anywhere in the CLAUDE.md
    backtick_file_regex = re.compile(r"`([^`]+\.(?:md|py|js|ts|sh|json|yaml|yml|txt))`")

    try:
        with open(claude_md_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                match = tier_regex.match(line.strip())
                if match:
                    tier_name = match.group(1)
                    file_list_str = match.group(2)
                    
                    files_in_tier = [f.strip() for f in file_list_str.split(',') if f.strip()]
                    
                    for rel_filepath in files_in_tier:
                        full_filepath = os.path.join(target_path, rel_filepath)
                        
                        if not os.path.exists(full_filepath):
                            print(colorize(f"Warning: File '{rel_filepath}' (mentioned in {CLAUDE_MD_FILENAME} line {line_num}) not found. Skipping.", COLOR_YELLOW), file=sys.stderr)
                            continue
                        
                        tokens, is_bin = count_tokens(full_filepath)
                        if is_bin:
                            print(colorize(f"Warning: File '{rel_filepath}' (mentioned in {CLAUDE_MD_FILENAME} line {line_num}) appears to be binary. Skipping token count.", COLOR_YELLOW), file=sys.stderr)
                            tokens = 0

                        tier_data[tier_name].append({
                            'path': rel_filepath,
                            'full_path': full_filepath,
                            'tokens': tokens
                        })
                        tier_totals[tier_name] += tokens
                        overall_total_tokens += tokens
    except Exception as e:
        print(colorize(f"Error reading or parsing '{claude_md_path}': {e}", COLOR_RED), file=sys.stderr)
        sys.exit(1)

    if args.format == 'json':
        json_output = {
            "claude_md_path": claude_md_path,
            "total_tokens": overall_total_tokens,
            "total_context_window": CLAUDE_MAX_CONTEXT,
            "percentage_of_window": (overall_total_tokens / CLAUDE_MAX_CONTEXT) * 100,
            "budget": args.budget,
            "tiers": {}
        }
        for tier_name in sorted(tier_data.keys()):
            json_output["tiers"][tier_name] = {
                "total_tokens": tier_totals[tier_name],
                "files": tier_data[tier_name]
            }
        print(json.dumps(json_output, indent=2))
    else:
        print(colorize(f"\n--- Tiered Context Budget from '{CLAUDE_MD_FILENAME}' ---", COLOR_BLUE))
        print(colorize(f"Budget: {args.budget} tokens", COLOR_CYAN))
        print(colorize(f"Claude Max Context: {CLAUDE_MAX_CONTEXT} tokens", COLOR_CYAN))
        print("-" * 80)

        for tier_name in sorted(tier_data.keys()):
            print(colorize(f"\n{tier_name}:", COLOR_BOLD + COLOR_MAGENTA))
            for item in tier_data[tier_name]:
                print(f"  {format_token_output(item['tokens'], args.budget)} {item['path']}")
            print(colorize(f"  Total for {tier_name}: {format_token_output(tier_totals[tier_name], args.budget)}", COLOR_BOLD))
            print("-" * 80)
        
        print(colorize(f"Overall Total: {format_token_output(overall_total_tokens, args.budget, CLAUDE_MAX_CONTEXT)}", COLOR_BOLD))
        print(colorize(f"Remaining budget: {args.budget - overall_total_tokens} tokens", get_color_for_tokens(overall_total_tokens, args.budget)))
        print("-" * 80)


# --- Main CLI Setup ---

def main():
    parser = argparse.ArgumentParser(
        description="Claude Context Budget Tool: Count tokens in files to manage Claude's 200K context window.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_BUDGET,
        help=f"Set a custom token budget for comparison (default: {DEFAULT_BUDGET})."
    )
    parser.add_argument(
        "--format",
        choices=['text', 'json'],
        default='text',
        help="Output format (default: text)."
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # Scan command
    scan_parser = subparsers.add_parser(
        "scan",
        help="Recursively list all files in a directory, sorted by token count.",
        description="Recursively scans a directory, counts tokens for each file, "
                    "and lists them sorted by token count (descending). "
                    "Skips common binary files and specified directories (.git, node_modules, etc.)."
    )
    scan_parser.add_argument(
        "path",
        type=str,
        help="The root directory to scan."
    )
    scan_parser.set_defaults(func=scan_command)

    # Check command
    check_parser = subparsers.add_parser(
        "check",
        help="Sum tokens for specific files and compare to budget.",
        description="Counts tokens for one or more specified files, "
                    "sums them up, and compares the total against the budget."
    )
    check_parser.add_argument(
        "files",
        type=str,
        nargs='+',
        help="One or more file paths to check."
    )
    check_parser.set_defaults(func=check_command)

    # Tier command
    tier_parser = subparsers.add_parser(
        "tier",
        help=f"Read {CLAUDE_MD_FILENAME} for tiered context definitions.",
        description=f"Looks for a '{CLAUDE_MD_FILENAME}' file in the specified path. "
                    f"If found, it parses lines like 'Tier 1: file1.py, dir/file2.js' "
                    f"to identify files belonging to different tiers (1, 2, or 3). "
                    f"It then counts tokens for each file and provides totals per tier and overall."
    )
    tier_parser.add_argument(
        "path",
        type=str,
        help=f"The directory containing the '{CLAUDE_MD_FILENAME}' file."
    )
    tier_parser.set_defaults(func=tier_command)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()