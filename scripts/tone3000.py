#!/usr/bin/env python3
"""List and download the NAM model files of a TONE3000 tone page.

  models TONE_URL                          list the models on the page with their direct .nam links
  download TONE_URL [--model TEXT] [--all] [--dest DIR]
                                           save .nam file(s); default folder: ~/Documents/NUX/NAM downloads/<tone title>

The direct links are the public files behind the page's own "Download Tone" button.
TONE3000 A2 files are 'SlimmableContainer' models (Full and Lite in one file); the MG-400 runs the Lite part.
"""
import argparse, json, os, re, sys, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (nux-mg400 skill)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def page_models(url):
    html = fetch(url).decode("utf-8", "replace")
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    title = re.sub(r"\s*NAM Profiles\s*$", "", title.group(1)).strip() if title else "tone3000"
    text = html.replace('\\"', '"')
    models, seen = [], set()
    for m in re.finditer(r'"name":"([^"]{1,200})","model_url":"(https://api\.tone3000\.com/storage/v1/object/public/models/[^"]+)"', text):
        name, link = m.group(1), m.group(2)
        if link not in seen:
            seen.add(link)
            models.append({"name": name, "url": link})
    if not models:
        sys.exit("No model files found on that page (is it a NAM tone page?).")
    return title, models


def safe(name):
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "tone"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("models"); p.add_argument("url")
    p = sub.add_parser("download"); p.add_argument("url"); p.add_argument("--model"); p.add_argument("--all", action="store_true")
    p.add_argument("--dest")
    a = ap.parse_args()

    title, models = page_models(a.url)
    if a.cmd == "models":
        print(title)
        for i, m in enumerate(models, 1):
            print(f"{i:>3}. {m['name']}\n     {m['url']}")
        return
    picked = models
    if a.model:
        picked = [m for m in models if a.model.lower() in m["name"].lower()]
    if not a.all and len(picked) != 1:
        names = "\n  ".join(m["name"] for m in picked or models)
        sys.exit(f"{len(picked)} models match; pass --model with a unique part of the name, or --all:\n  {names}")
    dest = a.dest or os.path.join(os.path.expanduser("~"), "Documents", "NUX", "NAM downloads", safe(title))
    os.makedirs(dest, exist_ok=True)
    for m in picked:
        data = fetch(m["url"])
        try:
            arch = json.loads(data).get("architecture")
        except ValueError:
            arch = "?"
        path = os.path.join(dest, safe(m["name"]) + ".nam")
        open(path, "wb").write(data)
        print(f"saved {path} ({len(data) // 1024} KB, architecture {arch})")


if __name__ == "__main__":
    main()
