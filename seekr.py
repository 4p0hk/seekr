#!/usr/bin/env python3
"""
first ever run:
1. setup.ps1

otherwise:
seekr.py -i tracks.json -d Z:\\music --score 80
"""
import sys
import importlib.util
import argparse
import json
import logging
import csv
import re
import subprocess
from pathlib import Path
from datetime import datetime

# -- ensure venv and dependencies exist ---------------------------------------
venv_dir = Path(__file__).parent / '.venv'
if venv_dir.exists() and not sys.prefix.startswith(str(venv_dir)):
    print("Warning: Virtual environment '.venv' is not active. Please activate it and retry.")
    sys.exit(1)
required = ['rapidfuzz', 'pyrekordbox', 'tabulate', 'colorama', 'tqdm']
missing = [m for m in required if importlib.util.find_spec(m) is None]
if missing:
    print(f"Missing dependencies: {', '.join(missing)}")
    print(f"Install with: pip install {' '.join(missing)}")
    sys.exit(1)

# core imports
from rapidfuzz import fuzz
from pyrekordbox import Rekordbox6Database
from tabulate import tabulate
from colorama import Fore, Style, init as colorama_init
from tqdm import tqdm

# initialize colorama
colorama_init(autoreset=True)

# patterns to strip out mix-annotations and feature-annotations
ORIGINAL_MIX_PATTERNS = ['(original mix)', 'original mix', '(orig mix)', 'orig mix']
FEAT_PATTERNS = [
    r"\(ft\.?.*?\)",    # "(ft. djinn)"
    r"\(feat\.?.*?\)",  # "(feat. djinn)"
    r",\s*ft\.?.*$",    # ", ft. djinn"
    r",\s*feat\.?.*$",  # ", feat. djinn"
    r"\s+ft\.?.*$",     # " ft. djinn"
    r"\s+feat\.?.*$",   # " feat. djinn"
]

def strip_mix_annotations(s):
    """Remove any 'original mix' variants."""
    t = s or ''
    for pat in ORIGINAL_MIX_PATTERNS:
        t = t.replace(pat, '') \
             .replace(pat.title(), '') \
             .replace(pat.upper(), '')
    return t.strip()

def strip_features(s):
    """Remove feature-annotations like 'ft. artist' or 'feat. artist'."""
    t = s or ''
    for pat in FEAT_PATTERNS:
        t = re.sub(pat, '', t, flags=re.IGNORECASE)
    return t.strip()

def norm(s):
    """Lowercase, strip mixes & features, trim."""
    t = (s or '').lower()
    t = strip_mix_annotations(t)
    t = strip_features(t)
    return t.strip()

def split_artists(s):
    """
    Split a multi-artist string into individual artist tokens.
    Splits on commas, &, '/', ';', or the word 'and'.
    """
    parts = re.split(r'[,&/;]|\band\b', s, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]

# setup logging
logger = logging.getLogger('seekr')
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S')
)
logger.addHandler(handler)

def setup_logging(debug):
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if debug:
        logger.debug(Fore.YELLOW + 'debug mode enabled')

def scan_rekordbox(contents, title, artist, score_cut):
    """
    Search the Rekordbox DB for matches to title and/or artist.
    Splits multi-artist entries and picks the best score.
    """
    results = []
    input_artists = split_artists(artist) if artist else ['']
    for c in contents:
        raw_title = getattr(c, 'Title', '') or ''
        raw_artist_obj = getattr(c, 'Artist', None)
        raw_artist = getattr(raw_artist_obj, 'Name', '') if raw_artist_obj else ''
        t_val = norm(raw_title)
        a_val = norm(raw_artist)
        db_artists = split_artists(a_val) or ['']

        best_score = 0
        if title and artist:
            for in_a in input_artists:
                for db_a in db_artists:
                    q = f"{title}::{in_a}"
                    d = f"{t_val}::{db_a}"
                    best_score = max(best_score, fuzz.token_set_ratio(q, d))
        elif title:
            best_score = fuzz.token_set_ratio(title, t_val)
        elif artist:
            for in_a in input_artists:
                for db_a in db_artists:
                    best_score = max(best_score, fuzz.token_set_ratio(in_a, db_a))

        if best_score >= score_cut:
            results.append({
                'score': best_score,
                'item': f"{raw_artist} - {raw_title}"
            })

    return sorted(results, key=lambda x: x['score'], reverse=True)

def scan_files(basepath, title, artist, score_cut):
    """
    Walk the filesystem under basepath, comparing filenames to title
    and any folder name in the path to artist. Returns high-scoring hits.
    """
    results = []
    seen = set()
    input_artists = split_artists(artist) if artist else ['']
    for f in basepath.rglob('*.*'):
        raw_name = f.stem
        file_name = norm(raw_name)
        rel_dirs = f.relative_to(basepath).parts[:-1]

        best_score = 0
        ok = False

        # title+artist
        if title and artist:
            t_score = fuzz.token_set_ratio(title, file_name)
            a_scores = []
            for d in rel_dirs:
                for db_a in split_artists(norm(d)):
                    for in_a in input_artists:
                        a_scores.append(fuzz.token_set_ratio(in_a, db_a))
            a_score = max(a_scores) if a_scores else 0
            if t_score >= score_cut and a_score >= score_cut:
                ok = True
                best_score = min(t_score, a_score)

        # title-only
        elif title:
            t_score = fuzz.token_set_ratio(title, file_name)
            if t_score >= score_cut:
                ok = True
                best_score = t_score

        # artist-only
        elif artist:
            a_scores = []
            for d in rel_dirs:
                for db_a in split_artists(norm(d)):
                    for in_a in input_artists:
                        a_scores.append(fuzz.token_set_ratio(in_a, db_a))
            a_score = max(a_scores) if a_scores else 0
            if a_score >= score_cut:
                ok = True
                best_score = a_score

        if ok:
            path = str(f.resolve())
            if path not in seen:
                seen.add(path)
                results.append({
                    'score': best_score,
                    'item': f.name,
                    'path': path
                })

    return sorted(results, key=lambda x: x['score'], reverse=True)

def main():
    ap = argparse.ArgumentParser(description='seekr: match tracks in Rekordbox & filesystem')
    ap.add_argument('-i', '--input',   required=True,               help='JSON file with title & artist')
    ap.add_argument('-d', '--dir',     help='root dir to search')
    ap.add_argument('--score',         type=int, default=80,        help='min similarity 0-100')
    ap.add_argument('--debug',         action='store_true',         help='enable debug logging')
    ap.add_argument('--verbose',       action='store_true',         help='detailed output')
    ap.add_argument('--report',        action='store_true',         help='generate JSON report')
    ap.add_argument('--dllist',        action='store_true',         help='generate download-list of missing items (CSV)')
    args = ap.parse_args()
    setup_logging(args.debug)

    # load & normalize input, skip blank rows
    try:
        raw = json.load(open(args.input, encoding='utf-8'))
    except Exception as e:
        logger.error(Fore.RED + f"input error: {e}")
        sys.exit(1)

    items = []
    for idx, row in enumerate(raw):
        rt = (row.get('title')  or '').strip()
        ra = (row.get('artist') or '').strip()
        t = norm(rt)
        a = norm(ra)
        if not (t or a):
            logger.debug(f"Skipping empty input row #{idx}")
            continue
        items.append({'title': t, 'artist': a})

    # --- Rekordbox bootstrap: SQLCipher install (ignore errors) + silent key grab ---
    try:
        subprocess.run(
            [sys.executable, '-m', 'pyrekordbox', 'install-sqlcipher'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except Exception:
        if args.debug:
            logger.debug("SQLCipher install attempt failed (ignored)")

    try:
        _ = next(iter(Rekordbox6Database().get_content()), None)
        if args.debug:
            logger.debug(Fore.YELLOW + "Rekordbox key bootstrap succeeded" + Style.RESET_ALL)
    except Exception as e:
        logger.error(Fore.RED + f"Rekordbox key bootstrap failed: {e}")
        sys.exit(1)

    # load rekordbox DB
    try:
        recs = list(Rekordbox6Database().get_content())
    except Exception as e:
        logger.error(Fore.RED + f"Rekordbox error: {e}")
        sys.exit(1)

    # process items
    results = []
    for row in tqdm(items, desc='Processing items', unit='item'):
        rb_hits = scan_rekordbox(recs, row['title'], row['artist'], args.score)
        fs_hits = scan_files(Path(args.dir), row['title'], row['artist'], args.score) if args.dir else []
        results.append({
            'artist':   row['artist'],
            'title':    row['title'],
            'rb_count': len(rb_hits),
            'fs_count': len(fs_hits),
            'rb_items': rb_hits,
            'fs_items': fs_hits
        })

    # summary counts
    rb_ct   = sum(r['rb_count'] > 0 for r in results)
    fs_ct   = sum(r['rb_count'] == 0 and r['fs_count'] > 0 for r in results)
    none_ct = sum(r['rb_count'] == 0 and r['fs_count'] == 0 for r in results)

    # print summary table
    print('\nSummary:')
    summary = [
        [Fore.GREEN + 'match in rb' + Style.RESET_ALL, rb_ct],
        [Fore.YELLOW + 'match on fs' + Style.RESET_ALL, fs_ct],
        [Fore.RED + 'no match'       + Style.RESET_ALL, none_ct]
    ]
    print(tabulate(summary, ['status', 'count'], tablefmt='grid'))

    # non-verbose: list no-match
    if not args.verbose:
        missing = [
            f"{r['artist']} - {r['title']}"
            for r in results
            if r['rb_count'] == 0 and r['fs_count'] == 0
        ]
        if missing:
            header = 'no match'
            print(f"\n{header}")
            print('-' * len(header))
            for m in missing:
                print(m)
            print('-' * len(header))
            print()

    # verbose output
    if args.verbose:
        print('\nDetailed summary:')
        rows = []
        for r in results:
            col = (
                Fore.GREEN if r['rb_count'] > 0
                else Fore.YELLOW if r['fs_count'] > 0
                else Fore.RED
            )
            rows.append([
                col + r['artist'] + Style.RESET_ALL,
                col + r['title']  + Style.RESET_ALL,
                col + str(r['rb_count']) + Style.RESET_ALL,
                col + str(r['fs_count']) + Style.RESET_ALL
            ])
        print(tabulate(rows, ['artist', 'title', 'rb_count', 'fs_count'], tablefmt='grid'))

        for r in results:
            term = f"{r['artist']} - {r['title']}".strip(' - ')
            if r['rb_count'] > 0:
                print(f"\n[{term}] Rekordbox matches ({r['rb_count']}):")
                for h in r['rb_items']:
                    print(f"  - {h['item']} (score {h['score']})")
            if r['fs_count'] > 0:
                print(f"\n[{term}] Filesystem matches ({r['fs_count']}):")
                for h in r['fs_items']:
                    print(f"  - {h['item']} (score {h['score']}) at {h['path']}")

    # download-list CSV
    if args.dllist:
        dl = [
            {'fetched': False, 'artist': r['artist'], 'title': r['title']}
            for r in results
            if r['rb_count'] == 0 and r['fs_count'] == 0
        ]
        if dl:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            out = f"{ts}_download-list.csv"
            with open(out, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['fetched', 'artist', 'title'])
                writer.writeheader()
                for row in dl:
                    writer.writerow(row)
            logger.info(Fore.GREEN + f"download-list: {out}")

    # JSON report
    if args.report:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = f"{ts}_report.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        logger.info(Fore.GREEN + f"report: {out}")

if __name__ == '__main__':
    main()
