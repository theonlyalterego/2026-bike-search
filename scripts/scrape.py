import json, os, re, sys
from datetime import datetime
from playwright.sync_api import sync_playwright

BIKES = [
    {"name": "Commencal Meta HT",      "query": "commencal+meta+ht"},
    {"name": "Rocky Mountain Growler", "query": "rocky+mountain+growler"},
    {"name": "Norco Torrent",         "query": "norco+torrent"},
    {"name": "Kona Honzo",            "query": "kona+honzo"},
    {"name": "Giant Fathom",          "query": "giant+fathom"},
    {"name": "Marin San Quentin",     "query": "marin+san+quentin"},
    {"name": "Specialized Fuse",      "query": "specialized+fuse"},
]

CL_URL = "https://washingtondc.craigslist.org/search/sss?query={q}#search=2~gallery~0"
PB_URL = "https://www.pinkbike.com/buysell/list/?lat=39.0503&lng=-77.3909&distance=50&q={q}"
OU_URL = "https://offerup.com/search?q={q}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def scrape_craigslist(page, query):
    q = query.replace("+", " ")
    page.goto(CL_URL.format(q=query), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    results = []
    cards = page.eval_on_selector_all("div.cl-search-result", """els => els.map(el => {
        const titleEl = el.querySelector('a.posting-title');
        const priceEl = el.querySelector('span.priceinfo');
        if (!titleEl) return null;
        return {
            title: (titleEl.textContent || '').trim(),
            url: titleEl.href || '',
            price: priceEl ? priceEl.textContent.trim() : '',
        };
    }).filter(x => x !== null)""")
    for c in cards:
        if q.lower() in c["title"].lower():
            results.append(c)
    return results


def scrape_pinkbike(page, query):
    q = query.replace("+", " ")
    page.goto(PB_URL.format(q=query), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    results = []
    items = page.eval_on_selector_all("table.bsitem-details", """els => els.map(el => {
        const tr = el.closest('tr');
        if (!tr) return null;
        const outer = tr.closest('table');
        if (!outer) return null;
        const links = outer.querySelectorAll('a');
        const imgs = outer.querySelectorAll('img');
        let title = '', url = '';
        for (const a of links) {
            if (a.href && a.href.includes('/buysell/') && a.textContent.trim()) {
                title = a.textContent.trim();
                url = a.href;
                break;
            }
        }
        const priceEl = el.querySelector('.bsitem-price');
        const price = priceEl ? priceEl.textContent.trim() : '';
        return {
            title: title,
            url: url,
            price: price,
            img: imgs.length > 0 ? imgs[0].src : '',
        };
    }).filter(x => x !== null)""")
    for i in items:
        if q.lower() in i["title"].lower():
            results.append(i)
    return results


def scrape_offerup(page, query):
    q = query.replace("+", " ")
    page.goto(OU_URL.format(q=query), wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    results = []
    items = page.eval_on_selector_all("a[href*='/item/detail/']", """els => els.slice(0, 50).map(el => {
        const text = el.textContent.trim();
        const img = el.querySelector('img');
        const match = text.match(/^(.*?)[$]\\s*(\\d[\\d,]*)/);
        let title = text, price = '';
        if (match) {
            title = match[1].trim();
            price = '$' + match[2];
        }
        return {
            title: title,
            url: el.href,
            price: price,
            img: img ? img.src : '',
        };
    })""")
    seen = set()
    for i in items:
        if q.lower() in i["title"].lower() and i["url"] not in seen:
            seen.add(i["url"])
            results.append(i)
    return results


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    output = {
        "fetched_at": datetime.now().isoformat(),
        "results": []
    }
    browser_context = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            """)

            for bike in BIKES:
                print(f"Scraping {bike['name']}...")
                try:
                    cl = scrape_craigslist(page, bike["query"])
                except Exception as e:
                    print(f"  Craigslist error: {e}")
                    cl = []
                try:
                    pb = scrape_pinkbike(page, bike["query"])
                except Exception as e:
                    print(f"  Pinkbike error: {e}")
                    pb = []
                try:
                    ou = scrape_offerup(page, bike["query"])
                except Exception as e:
                    print(f"  OfferUp error: {e}")
                    ou = []

                output["results"].append({
                    "bike_name": bike["name"],
                    "sources": {
                        "craigslist": cl,
                        "pinkbike": pb,
                        "offerup": ou,
                    }
                })
                print(f"  CL:{len(cl)} PB:{len(pb)} OU:{len(ou)}")

            browser.close()

        path = os.path.join(DATA_DIR, "listings.json")
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nWritten {path}")
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
