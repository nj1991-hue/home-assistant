#!/usr/bin/env python3
"""Rayo (RadioPlay DK) live stream relay.

Resolves a station's stream URL from rayo.dk and pipes the audio to stdout
(or a file), with automatic reconnect. Designed to run continuously.

Stream resolution
-----------------
rayo.dk is a Next.js app that embeds full station data (including every
stream variant) in a __NEXT_DATA__ JSON blob on each station page.
We parse that and pick the best variant for the requested tier.

Premium auth
------------
As of this writing, the premium ad-free URLs are served by the CDN
(live-bauerdk.sharp-stream.com) without authentication — the "premium"
gating happens in the web/app player UI, not at the audio edge. Verified
both while logged in and after logout: the CDN returns the same audio
either way. The script tries the premium URL anonymously by default.

If Bauer ever locks the CDN down, --free will fall back to the
ad-supported stream, and an OAuth login step would need adding (see
TODO marker below).

Usage
-----
    # Print the URL only
    python3 rayo_stream.py --print-url

    # Stream Radio Vinyl premium to stdout, pipe into ffmpeg/icecast/whatever
    python3 rayo_stream.py | ffmpeg -i - -c copy output.aac

    # Or write to a file with automatic reconnect on drop
    python3 rayo_stream.py -o radio_vinyl.aac

    # Pick a different station, or fall back to the free (ad-supported) stream
    python3 rayo_stream.py nova --free
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (rayo-stream-relay)"
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _fetch_next_data(slug: str) -> dict:
    """Fetch a station page and return the parsed __NEXT_DATA__ JSON."""
    req = Request(f"https://rayo.dk/{slug}", headers={"User-Agent": UA})
    with urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError("Could not find __NEXT_DATA__ — site layout may have changed")
    return json.loads(match.group(1))


def resolve_station(slug: str) -> dict:
    """Fetch a station page and return its data dict from __NEXT_DATA__."""
    return _fetch_next_data(slug)["props"]["initialState"]["station"]["data"]


def list_all_slugs(seed_slug: str = "radiovinyl") -> list[str]:
    """Return every station slug Rayo currently lists.

    Any station page carries the full station directory in its NEXT_DATA,
    so one fetch is enough.
    """
    data = _fetch_next_data(seed_slug)
    items = data["props"]["initialState"]["stationList"]["items"]
    return list(items)


def pick_stream(station: dict, *, premium: bool) -> str:
    """Pick the best stream URL for the requested tier."""
    streams = station.get("stationStreams", [])
    candidates = [s for s in streams if bool(s.get("streamPremium")) == premium]
    if not candidates:
        raise RuntimeError(
            f"No {'premium' if premium else 'free'} streams listed for this station"
        )

    def score(s: dict) -> tuple:
        # Prefer high quality, then higher bitrate.
        return (
            s.get("streamQuality") == "hq",
            s.get("streamBitRate") or 0,
        )

    return max(candidates, key=score)["streamUrl"]


# TODO: if Bauer ever requires auth for the premium stream, implement OAuth here.
# Login is handled client-side via JS in the SPA at https://rayo.dk/login.
# Tracing it would mean reverse-engineering the XHR calls (likely against
# *.bauerradio.com or *.planetradio.co.uk) to get a bearer token, then
# adding `Authorization: Bearer ...` to the stream request below.


def relay(stream_url: str, sink, *, chunk: int = 8192) -> None:
    """Pipe audio bytes from stream_url to sink. Returns if the server closes."""
    req = Request(stream_url, headers={"User-Agent": UA, "Icy-MetaData": "0"})
    with urlopen(req, timeout=15) as resp:
        while True:
            buf = resp.read(chunk)
            if not buf:
                return
            sink.write(buf)
            sink.flush()


def dump_all(out_path: str, *, sleep: float = 0.3) -> None:
    """Walk every station slug and write a JSON map to out_path.

    Output shape:
        {
          "<slug>": {
            "name": "Radio Vinyl",
            "image_url": "https://...450x450/425.jpg",  # square station logo
            "premium_url": "https://...",   # may be null
            "free_url": "https://...",      # may be null
          },
          ...
        }
    """
    slugs = list_all_slugs()
    print(f"[rayo] {len(slugs)} stations to fetch", file=sys.stderr)

    result: dict[str, dict] = {}
    for i, slug in enumerate(slugs, 1):
        try:
            station = resolve_station(slug)
        except Exception as e:
            print(f"[rayo] [{i:2}/{len(slugs)}] {slug}: FAILED ({e})", file=sys.stderr)
            continue

        def maybe(premium: bool) -> str | None:
            try:
                return pick_stream(station, premium=premium)
            except RuntimeError:
                return None

        entry = {
            "name": station.get("stationName"),
            "image_url": station.get("stationSquareLogo")
                         or station.get("stationListenBarLogo"),
            "premium_url": maybe(True),
            "free_url": maybe(False),
        }
        result[slug] = entry
        tier_summary = []
        if entry["premium_url"]:
            tier_summary.append("premium")
        if entry["free_url"]:
            tier_summary.append("free")
        print(f"[rayo] [{i:2}/{len(slugs)}] {slug:30} {entry['name']:30} "
              f"[{', '.join(tier_summary) or 'no streams'}]", file=sys.stderr)
        time.sleep(sleep)  # be polite

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[rayo] wrote {out_path} ({len(result)} stations)", file=sys.stderr)


def run(slug: str, *, premium: bool, out_path: str | None) -> int:
    station = resolve_station(slug)
    stream_url = pick_stream(station, premium=premium)
    tier = "premium" if premium else "free"
    print(f"[rayo] {station.get('stationName')} ({slug}) — {tier} stream",
          file=sys.stderr)
    print(f"[rayo] {stream_url}", file=sys.stderr)

    sink = open(out_path, "ab") if out_path else sys.stdout.buffer

    # Reconnect loop with capped exponential backoff.
    backoff = 1.0
    try:
        while True:
            try:
                relay(stream_url, sink)
                print("[rayo] connection closed, reconnecting...", file=sys.stderr)
                backoff = 1.0
            except (HTTPError, URLError, ConnectionError, TimeoutError) as e:
                print(f"[rayo] connection error: {e}; retrying in {backoff:.1f}s",
                      file=sys.stderr)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
            except BrokenPipeError:
                # Downstream consumer hung up (e.g. ffmpeg closed). We're done.
                return 0
    finally:
        if out_path:
            sink.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("slug", nargs="?", default="radiovinyl",
                   help="Station slug from the rayo.dk URL (default: radiovinyl)")
    p.add_argument("--free", action="store_true",
                   help="Use the ad-supported free stream instead of premium")
    p.add_argument("-o", "--output",
                   help="Append audio to this file instead of stdout")
    p.add_argument("--print-url", action="store_true",
                   help="Just print the stream URL and exit (don't relay)")
    p.add_argument("--dump-all", metavar="FILE",
                   help="Fetch every station and write a slug→URL JSON map to FILE")
    args = p.parse_args()

    premium = not args.free

    if args.dump_all:
        dump_all(args.dump_all)
        return 0

    if args.print_url:
        station = resolve_station(args.slug)
        print(pick_stream(station, premium=premium))
        return 0

    # Make Ctrl+C exit cleanly without a noisy traceback.
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    return run(args.slug, premium=premium, out_path=args.output)


if __name__ == "__main__":
    sys.exit(main())
