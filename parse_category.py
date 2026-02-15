# pip install requests beautifulsoup4 lxml

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://food.ru"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


WS_RE = re.compile(r"\s+")


def clean_text(s: str) -> str:
    return WS_RE.sub(" ", (s or "")).strip()


@dataclass
class Subcategory:
    name: str
    url: str  # absolute


@dataclass
class Category:
    name: str
    url: str  # absolute
    subcategories: List[Subcategory]


def fetch_html(url: str, timeout: int = 25) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_categories_and_subcategories(html: str, base_url: str = BASE_URL) -> List[Category]:
    """
    На food.ru меню устроено как набор блоков:
      div[class*="twoTieredSubCategory_wrapper__"]
        a[class*="twoTieredSubCategory_subCategory__"]      (категория)
        a[class*="twoTieredSubCategory_innerCategory__"]    (подкатегории)
    """
    soup = BeautifulSoup(html, "lxml")

    categories: List[Category] = []
    seen_cat = set()
    seen_sub = set()

    wrappers = soup.select('div[class*="twoTieredSubCategory_wrapper__"]')

    for w in wrappers:
        cat_a = w.select_one('a[class*="twoTieredSubCategory_subCategory__"][href]')
        if not cat_a:
            continue

        cat_name = clean_text(cat_a.get_text(" ", strip=True))
        cat_href = cat_a.get("href", "").strip()
        if not cat_name or not cat_href:
            continue

        cat_url = urljoin(base_url, cat_href)

        # дедуп категории по URL
        if cat_url in seen_cat:
            continue
        seen_cat.add(cat_url)

        subcats: List[Subcategory] = []
        for a in w.select('a[class*="twoTieredSubCategory_innerCategory__"][href]'):
            name = clean_text(a.get_text(" ", strip=True))
            href = a.get("href", "").strip()
            if not name or not href:
                continue

            # отсекаем ссылки на конкретные рецепты (у них после /recipes/ идёт цифра)
            # нам нужны именно подкатегории
            path = href.split("?", 1)[0]
            if path.startswith("/recipes/"):
                tail = path[len("/recipes/"):]
                if tail and tail[0].isdigit():
                    continue

            url = urljoin(base_url, href)

            key = (cat_url, url)
            if key in seen_sub:
                continue
            seen_sub.add(key)

            subcats.append(Subcategory(name=name, url=url))

        categories.append(Category(name=cat_name, url=cat_url, subcategories=subcats))

    # Fallback, если классы вдруг поменяются: соберём всё /recipes/<slug> (не рецепты)
    if not categories:
        # группировка по "категории" в этом режиме будет условной
        links = []
        for a in soup.select('a[href^="/recipes/"][href]'):
            href = a.get("href", "").strip()
            text = clean_text(a.get_text(" ", strip=True))
            if not href or not text:
                continue
            tail = href[len("/recipes/"):]
            if tail and tail[0].isdigit():
                continue
            links.append((text, urljoin(base_url, href)))

        # складываем всё в одну “категорию”
        uniq = {}
        for name, url in links:
            uniq[url] = name
        categories = [
            Category(
                name="Рецепты",
                url=urljoin(base_url, "/recipes"),
                subcategories=[Subcategory(name=n, url=u) for u, n in sorted(uniq.items())],
            )
        ]

    return categories


def main(
    out_file: str = "categories_and_subcategories.json",
    seed_url: Optional[str] = "https://food.ru/recipes/zakuski/rulety",
    html_file: Optional[str] = None,
):
    if html_file:
        html = Path(html_file).read_text(encoding="utf-8", errors="ignore")
        source = str(Path(html_file).resolve())
    else:
        if not seed_url:
            raise ValueError("Нужно указать seed_url или html_file.")
        html = fetch_html(seed_url)
        source = seed_url

    cats = extract_categories_and_subcategories(html)

    payload = {
        "source": source,
        "base_url": BASE_URL,
        "categories": [asdict(c) for c in cats],
    }

    Path(out_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: сохранено в {out_file} | категорий: {len(cats)}")


if __name__ == "__main__":
    # Вариант А: из интернета
    main(
        out_file="categories_and_subcategories.json",
        seed_url="https://food.ru/recipes/zakuski/rulety",
        html_file=None,
    )

    # Вариант Б: из локального HTML (раскомментируй)
    # main(
    #     out_file="categories_and_subcategories.json",
    #     seed_url=None,
    #     html_file="rulety.html",
    # )
