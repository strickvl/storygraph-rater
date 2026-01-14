#!/usr/bin/env python3
"""
Simple server that serves static files AND saves ratings to disk.
Ratings are saved to data/ratings.json on every update.
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

RATINGS_FILE = Path(__file__).parent / "data" / "ratings.json"


class RatingHandler(SimpleHTTPRequestHandler):
    """Extends SimpleHTTPRequestHandler with a POST endpoint for saving ratings."""

    def do_POST(self):
        if self.path == "/api/rate":
            self._handle_rate()
        else:
            self.send_error(404, "Not Found")

    def _handle_rate(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            # Validate the data structure
            if "book_id" not in data or "rating" not in data:
                self.send_error(400, "Missing book_id or rating")
                return

            if data["rating"] not in ("yes", "no", "skip"):
                self.send_error(400, "Rating must be 'yes', 'no', or 'skip'")
                return

            # Load existing ratings
            ratings = {}
            if RATINGS_FILE.exists():
                with open(RATINGS_FILE, "r") as f:
                    ratings = json.load(f)

            # Update with new rating
            ratings[data["book_id"]] = data["rating"]

            # Save back to file
            RATINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(RATINGS_FILE, "w") as f:
                json.dump(ratings, f, indent=2)

            # Send success response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "total_ratings": len(ratings)}).encode())

            print(f"  ✓ Saved rating: {data['book_id']} = {data['rating']} ({len(ratings)} total)")

        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        # Add CORS headers to all responses
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def main():
    port = 8000
    server_address = ("0.0.0.0", port)

    # Load existing ratings count
    rating_count = 0
    if RATINGS_FILE.exists():
        with open(RATINGS_FILE, "r") as f:
            rating_count = len(json.load(f))

    print(f"\n📚 Book Rating Server")
    print(f"   Local:   http://localhost:{port}")
    print(f"   Network: http://0.0.0.0:{port}")
    print(f"   Ratings: {RATINGS_FILE} ({rating_count} saved)")
    print(f"\n   Press Ctrl+C to stop\n")

    httpd = HTTPServer(server_address, RatingHandler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
