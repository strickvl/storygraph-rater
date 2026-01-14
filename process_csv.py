#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
"""
Process StoryGraph CSV export and prepare data for satisfaction annotation.

Usage:
    uv run process_csv.py path/to/storygraph_export.csv

Output:
    Creates data/books.json with enriched book data including cover URLs.
"""

import csv
import json
import random
import sys
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TypedDict, Optional
from datetime import datetime


class Book(TypedDict):
    id: str
    title: str
    authors: str
    year_read: int
    date_read: Optional[str]  # Full date in YYYY-MM-DD format
    isbn: Optional[str]
    cover_url: Optional[str]
    format: Optional[str]


def parse_date(date_str: str) -> tuple[Optional[int], Optional[str]]:
    """
    Parse date string and return (year, full_date_iso).
    Full date is in YYYY-MM-DD format when available.
    """
    if not date_str or date_str.strip() == "":
        return None, None

    # Try common formats
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.year, dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try year-only format
    try:
        dt = datetime.strptime(date_str.strip(), "%Y")
        return dt.year, None  # No full date available
    except ValueError:
        pass

    # Last resort: look for a 4-digit year anywhere in the string
    import re
    match = re.search(r'\b(19|20)\d{2}\b', date_str)
    if match:
        return int(match.group()), None

    return None, None


def parse_year_from_date(date_str: str) -> Optional[int]:
    """Extract year from various date formats StoryGraph uses."""
    year, _ = parse_date(date_str)
    return year


def fetch_cover_by_search(title: str, author: str, max_retries: int = 3) -> Optional[str]:
    """
    Search Open Library for a cover by title/author.
    Uses exponential backoff with jitter for polite retrying.
    """
    query = urllib.parse.quote(f"{title} {author}")
    search_url = f"https://openlibrary.org/search.json?q={query}&limit=1"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "BookSatisfactionApp/1.0 (polite crawler)"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

                if data.get("docs") and len(data["docs"]) > 0:
                    doc = data["docs"][0]
                    if "cover_i" in doc:
                        return f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                    if "isbn" in doc and doc["isbn"]:
                        return f"https://covers.openlibrary.org/b/isbn/{doc['isbn'][0]}-M.jpg"
            return None

        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter: 1s, 2s, 4s base + random 0-1s
                delay = (2 ** attempt) + random.random()
                time.sleep(delay)
            else:
                return None

    return None


def verify_isbn_cover(isbn: str, max_retries: int = 2) -> Optional[str]:
    """
    Check if an ISBN has a real cover (not a 1x1 placeholder).
    Returns the URL if valid, None otherwise.
    """
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                method='HEAD',
                headers={"User-Agent": "BookSatisfactionApp/1.0 (polite crawler)"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                # Open Library returns a tiny image (< 1KB) for missing covers
                content_length = response.headers.get('Content-Length', '0')
                if int(content_length) > 1000:  # Real covers are > 1KB
                    return url
            return None
        except Exception:
            if attempt < max_retries - 1:
                delay = (2 ** attempt) + random.random()
                time.sleep(delay)
    return None


def fetch_cover_for_book(book: Book) -> tuple[str, Optional[str]]:
    """
    Fetch cover URL for a single book. Returns (book_id, cover_url).
    Verifies ISBN covers exist, falls back to search if not.
    """
    # Try ISBN first
    if book["isbn"]:
        cover_url = verify_isbn_cover(book["isbn"])
        if cover_url:
            return (book["id"], cover_url)

    # Fall back to search
    cover_url = fetch_cover_by_search(book["title"], book["authors"])
    return (book["id"], cover_url)


def clean_isbn(isbn_str: Optional[str]) -> Optional[str]:
    """Clean and validate ISBN string."""
    if not isbn_str:
        return None

    cleaned = "".join(c for c in isbn_str if c.isdigit() or c.upper() == "X")

    if len(cleaned) in (10, 13):
        return cleaned

    return None


def process_csv(csv_path: Path) -> list[Book]:
    """Process StoryGraph CSV and return list of books."""
    books: list[Book] = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        fieldnames = reader.fieldnames or []
        print(f"Found columns: {fieldnames}", file=sys.stderr)

        for i, row in enumerate(reader):
            def get_col(possible_names: list[str]) -> str:
                for name in possible_names:
                    for col in row.keys():
                        if col.lower().strip() == name.lower():
                            return row[col]
                return ""

            title = get_col(["title", "book title"])
            authors = get_col(["authors", "author", "author(s)"])
            read_status = get_col(["read status", "status", "exclusive shelf"])
            date_read = get_col(["last date read", "date read", "dates read", "date finished"])
            isbn = get_col(["isbn/uid", "isbn", "isbn13", "isbn-13"])
            book_format = get_col(["format", "binding"])

            if read_status.lower() not in ["read", "finished"]:
                continue

            year, full_date = parse_date(date_read)
            if not year:
                dates_read = get_col(["dates read"])
                if dates_read:
                    parts = dates_read.split("-")
                    year, full_date = parse_date(parts[-1].strip())

            if not year:
                print(f"  Warning: No year found for '{title}', skipping", file=sys.stderr)
                continue

            clean_isbn_val = clean_isbn(isbn)

            book: Book = {
                "id": f"book_{i}",
                "title": title.strip(),
                "authors": authors.strip(),
                "year_read": year,
                "date_read": full_date,
                "isbn": clean_isbn_val,
                "cover_url": None,
                "format": book_format.strip() if book_format else None,
            }

            books.append(book)

    return books


def enrich_with_covers(books: list[Book], max_workers: int = 10) -> list[Book]:
    """
    Add cover URLs to books using parallel requests.

    All books are verified - ISBN covers are checked via HEAD request,
    missing ones fall back to search.
    """
    total = len(books)
    books_with_isbn = sum(1 for b in books if b["isbn"])

    print(f"  {books_with_isbn} books have ISBNs (will verify)", file=sys.stderr)
    print(f"  {total - books_with_isbn} books need search", file=sys.stderr)
    print(f"  Using {max_workers} parallel workers", file=sys.stderr)

    book_lookup = {b["id"]: b for b in books}
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_cover_for_book, book): book
            for book in books
        }

        for future in as_completed(futures):
            book_id, cover_url = future.result()
            book_lookup[book_id]["cover_url"] = cover_url
            completed += 1

            if completed % 50 == 0 or completed == total:
                print(f"  Processed {completed}/{total} books...", file=sys.stderr)

    return books


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run process_csv.py path/to/storygraph_export.csv", file=sys.stderr)
        print("\nThis will create data/books.json with your processed reading data.", file=sys.stderr)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"Error: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(__file__).parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "books.json"

    print(f"Processing: {csv_path}", file=sys.stderr)

    # Step 1: Parse CSV
    print("\n[1/2] Parsing CSV...", file=sys.stderr)
    books = process_csv(csv_path)
    print(f"  Found {len(books)} read books", file=sys.stderr)

    if not books:
        print("Error: No books found. Check that your CSV has 'read' status books.", file=sys.stderr)
        sys.exit(1)

    # Step 2: Fetch cover URLs
    print("\n[2/2] Fetching cover images...", file=sys.stderr)
    skip_covers = "--no-covers" in sys.argv
    if skip_covers:
        print("  Skipping cover fetch (--no-covers flag)", file=sys.stderr)
    else:
        books = enrich_with_covers(books, max_workers=5)

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved {len(books)} books to: {output_path}", file=sys.stderr)

    # Summary stats
    years = sorted(set(b["year_read"] for b in books))
    print(f"  Years covered: {min(years)} - {max(years)}", file=sys.stderr)
    books_with_covers = sum(1 for b in books if b["cover_url"])
    print(f"  Books with covers: {books_with_covers}/{len(books)}", file=sys.stderr)


if __name__ == "__main__":
    main()
