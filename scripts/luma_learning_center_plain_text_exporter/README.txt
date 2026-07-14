Luma Learning Center Plain-Text Exporter
=======================================

I was able to verify the public Learning Center article index at:
https://lumalabs.ai/learning-center/articles

The server-rendered version I can access exposes 28 article links, even though you mentioned 40. This package is built to handle both cases:

1. It includes the 28 visible article URLs I could confirm.
2. It can also run browser-based discovery with Playwright, which should catch client-side-only/lazy-loaded articles if your browser view shows all 40.

Quick run
---------

From this folder:

python -m pip install -r requirements.txt
python export_luma_learning_center_articles.py

Browser-rendered discovery
--------------------------

If the basic run finds only 28 and your browser shows 40:

python -m pip install -r requirements.txt
python -m playwright install chromium
python export_luma_learning_center_articles.py --browser

Output
------

The script creates:

luma_learning_center_plain_text_articles/
  01_article-title.txt
  02_article-title.txt
  ...
  manifest.csv

Each .txt file contains:
- Article title
- Source URL
- Extracted plain text article body

Notes
-----

This package does not include copied article bodies because the sandbox environment here could browse the page but could not directly save the site HTML into local files. Running this locally should create the actual plain-text files in one pass.
