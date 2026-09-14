#!/usr/bin/env python3
"""Resource-relative entry point; works from any current directory."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from geo_article_studio.cli import main
if __name__=='__main__':
    raise SystemExit(main())
