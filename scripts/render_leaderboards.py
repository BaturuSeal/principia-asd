"""Refresh portable HTML from already exported, frozen numerical records."""

import argparse
import json
from pathlib import Path

from principia_asd.report_html import render_leaderboards

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--leaderboard-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(render_leaderboards(args.leaderboard_root, args.data_root)))
