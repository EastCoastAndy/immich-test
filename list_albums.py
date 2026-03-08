"""
list_albums.py - Browse Immich albums from the command line.

Reads connection settings from config.ini, then:
  1. Lists all albums with their asset counts.
  2. Lets you pick an album number to see its individual files.

To add a new feature, add a method to ImmichClient (API layer) and
a matching display function below (display layer), then call it from main().
"""

import configparser
import sys
import urllib3
import requests
from collections import Counter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

def load_config(path="config.ini"):
    """Read config.ini and return the [immich] section."""
    config = configparser.ConfigParser()
    config.read(path)
    if "immich" not in config:
        print("ERROR: [immich] section not found in config.ini")
        sys.exit(1)
    return config["immich"]


# ---------------------------------------------------------------------------
# API LAYER  –  one method per Immich API call
#
# To add a new API call, add a method here following the same pattern.
# Example:
#     def get_all_assets(self):
#         return self._get("/api/assets")
# ---------------------------------------------------------------------------

class ImmichClient:
    """Handles all communication with the Immich server."""

    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key, "Accept": "application/json"}

    def _get(self, path):
        """Make a GET request to the Immich API and return the JSON response."""
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            verify=False,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_albums(self):
        """Return a list of all albums (summary info, no asset details)."""
        return self._get("/api/albums")

    def get_album_detail(self, album_id):
        """Return full details for one album, including its asset list."""
        return self._get(f"/api/albums/{album_id}")


# ---------------------------------------------------------------------------
# DISPLAY LAYER  –  one function per thing shown on screen
#
# To add a new display, add a function here.
# Example:
#     def print_asset_detail(asset):
#         ...
# ---------------------------------------------------------------------------

def print_albums(albums):
    """Print a numbered table of albums with asset counts. Returns column width."""
    max_name_len = max(len(a.get("albumName", "")) for a in albums)
    col_width = max(max_name_len, 10)

    print(f"\n  {'#':>3}  {'Album Name':<{col_width}}  {'Assets':>6}")
    print(f"  {'-'*3}  {'-'*col_width}  {'-'*6}")

    total_assets = 0
    for i, album in enumerate(albums, 1):
        name  = album.get("albumName", "(unnamed)")
        count = album.get("assetCount", 0)
        total_assets += count
        print(f"  {i:>3}  {name:<{col_width}}  {count:>6}")

    print(f"  {'-'*3}  {'-'*col_width}  {'-'*6}")
    print(f"  {'':>3}  {'TOTAL  ' + str(len(albums)) + ' albums':<{col_width}}  {total_assets:>6}\n")
    return col_width


def count_duplicates(assets):
    """Return (checksum_dupes, filename_dupes): assets sharing checksum / sharing filename."""
    checksum_counts = Counter(a.get("checksum") for a in assets if a.get("checksum"))
    fname_counts    = Counter(a.get("originalFileName") for a in assets if a.get("originalFileName"))
    checksum_dupes = sum(1 for a in assets if checksum_counts.get(a.get("checksum", ""), 0) > 1)
    fname_dupes    = sum(1 for a in assets if fname_counts.get(a.get("originalFileName", ""), 0) > 1)
    return checksum_dupes, fname_dupes


def print_album_detail(album_detail):
    """Print every asset in an album, sorted by date taken."""
    assets = album_detail.get("assets", [])
    name   = album_detail.get("albumName", "(unnamed)")

    if not assets:
        print("  (no assets in this album)\n")
        return

    # Sort by date taken
    assets.sort(key=lambda a: a.get("localDateTime", a.get("fileCreatedAt", "")))

    fname_width = max((len(a.get("originalFileName", "")) for a in assets), default=10)
    fname_width = max(fname_width, 20)

    photos = sum(1 for a in assets if a.get("type") == "IMAGE")
    videos = sum(1 for a in assets if a.get("type") == "VIDEO")
    checksum_dupes, fname_dupes = count_duplicates(assets)

    dupe_str = f", duplicates: {checksum_dupes} checksum / {fname_dupes} filename"
    print(f"\n  Album: {name}  ({photos} photo{'s' if photos != 1 else ''}, "
          f"{videos} video{'s' if videos != 1 else ''}{dupe_str})\n")
    print(f"  {'#':>4}  {'File Name':<{fname_width}}  {'Date Taken':<19}  Type")
    print(f"  {'-'*4}  {'-'*fname_width}  {'-'*19}  ----")

    for i, asset in enumerate(assets, 1):
        fname    = asset.get("originalFileName", "(unknown)")
        raw_dt   = asset.get("localDateTime") or asset.get("fileCreatedAt", "")
        date_str = raw_dt[:19].replace("T", " ") if raw_dt else "unknown"
        icon     = {"IMAGE": "IMG", "VIDEO": "VID"}.get(asset.get("type", ""), "???")
        print(f"  {i:>4}  {fname:<{fname_width}}  {date_str:<19}  {icon}")

    print()


def print_album_list_compact(albums, col_width):
    """Print a compact numbered list of album names (shown after a detail view)."""
    print(f"  {'#':>3}  {'Album Name':<{col_width}}")
    print(f"  {'-'*3}  {'-'*col_width}")
    for i, a in enumerate(albums, 1):
        print(f"  {i:>3}  {a.get('albumName', '(unnamed)')}")
    print()


# ---------------------------------------------------------------------------
# MAIN  –  program flow
# ---------------------------------------------------------------------------

def main():
    cfg      = load_config()
    client   = ImmichClient(cfg["url"], cfg["apikey"])

    print(f"Connecting to Immich at {client.base_url} ...\n")

    try:
        albums = client.get_albums()
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to the Immich server.")
        print(f"  URL used: {client.base_url}")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code} - {e.response.text}")
        sys.exit(1)

    if not albums:
        print("No albums found.")
        return

    albums.sort(key=lambda a: a.get("albumName", "").lower())
    col_width = print_albums(albums)

    # Interactive loop: pick an album number to drill into
    while True:
        try:
            choice = input("  Enter album number to view details (or press Enter to quit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not choice:
            break

        if not choice.isdigit() or not (1 <= int(choice) <= len(albums)):
            print(f"  Please enter a number between 1 and {len(albums)}.\n")
            continue

        album_id = albums[int(choice) - 1]["id"]

        try:
            detail = client.get_album_detail(album_id)
        except requests.exceptions.HTTPError as e:
            print(f"  ERROR fetching album: {e}\n")
            continue

        print_album_detail(detail)
        print_album_list_compact(albums, col_width)


if __name__ == "__main__":
    main()
