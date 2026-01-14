# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Book Satisfaction Tracker — a personal tool to rate your reading choices (satisfied/unsatisfied) and visualize satisfaction trends over time. Uses StoryGraph CSV exports as the data source.

## Architecture

```
storygraph-rater/
├── process_csv.py      # Python: CSV→JSON converter with parallel cover fetching
├── server.py           # Python: HTTP server with POST endpoint to save ratings
├── index.html          # Rating UI: swipeable card interface (Tinder-style)
├── visualization.html  # Results UI: Chart.js charts and statistics
└── data/
    ├── *.csv           # StoryGraph export (input)
    ├── books.json      # Generated book data with cover URLs (output)
    └── ratings.json    # User ratings, saved on every rating (auto-generated)
```

**Data flow:**
1. User exports CSV from StoryGraph
2. `process_csv.py` parses CSV, fetches covers (parallel with backoff), outputs `data/books.json`
3. `server.py` serves files AND accepts POST to `/api/rate` to save ratings to disk
4. `index.html` loads JSON, presents books in random order for Yes/No/Skip rating
5. Ratings saved to `data/ratings.json` on disk (also backed up to localStorage)
6. `visualization.html` reads both JSON files to render charts

## Common Commands

```bash
# Process StoryGraph export (creates data/books.json)
uv run process_csv.py data/storygraph_export.csv

# Skip cover image fetching (faster)
uv run process_csv.py data/storygraph_export.csv --no-covers

# Run local server (saves ratings to data/ratings.json)
python3 server.py

# For phone access through VPN, use cloudflared tunnel
cloudflared tunnel --url http://localhost:8000
```

## Key Technical Details

- **No build step**: Vanilla HTML/CSS/JS frontend, no npm/bundler
- **Simple Python backend**: `server.py` serves files + saves ratings via POST `/api/rate`
- **Cover images**: Open Library API with ISBN lookup, falls back to title/author search
- **ISBN verification**: HEAD requests check Content-Length > 1KB to avoid 1x1 placeholder images
- **Parallel fetching**: ThreadPoolExecutor with exponential backoff + jitter for polite API usage
- **Date parsing**: Handles multiple StoryGraph date formats plus regex fallback for year extraction

## Frontend State

Both HTML files share state via:
- `data/books.json` — book metadata (title, author, year, ISBN, cover_url, date_read)
- `data/ratings.json` — ratings saved to disk on every rating
- `localStorage.bookSatisfactionRatings` — backup fallback for ratings

The rating interface shuffles book order to prevent temporal bias.

## Visualization Page

`visualization.html` uses Chart.js with the date-fns adapter for time-based charts. Key features:

- **MIN_YEAR config**: Set `const MIN_YEAR = 2012;` at top of script to filter all charts/stats to a specific year range
- **Summary cards**: Total books, satisfaction %, best/worst years (all respect MIN_YEAR)
- **Year-by-year chart**: Bar chart (volume) + line (satisfaction %) overlay
- **Heatmap**: GitHub-style grid showing satisfaction by week across years (flex-based, full-width)
- **Cumulative satisfaction**: Time-scale line chart tracking rolling satisfaction rate
- **Streak analysis**: Longest runs of satisfied/unsatisfied reads with human-readable dates
- **Volume vs Pickiness**: Scatter plot correlating reading volume with satisfaction
- **Author loyalty**: Cards showing satisfaction rates for frequently-read authors (3+ books)
