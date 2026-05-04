# foodru_pipeline.py
# pip install requests beautifulsoup4 lxml

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

import parse_html  # модуль pipeline/parse_html.py


BASE_DEFAULT = "https://food.ru"
RECIPE_HREF_RE = re.compile(r"^/recipes/\d+-")  # рецепты вида /recipes/12345-...


# -----------------------------
# Utils
# -----------------------------
def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def load_set(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    return {x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}


def url_to_cache_path(cache_dir: Path, kind: str, url: str) -> Path:
    u = urlparse(url)
    tail = (u.path.strip("/").split("/")[-1] or "index")[:60]
    tail = re.sub(r"[^a-zA-Z0-9_-]+", "_", tail)
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return cache_dir / kind / f"{tail}_{h}.html"


def is_recipe_href(href: str) -> bool:
    return bool(RECIPE_HREF_RE.match(href))


def looks_like_listing(url: str) -> bool:
    """
    Оставляем только страницы-списки /recipes/<slug>/<slug>...
    Отсекаем /recipes/<digits>-...
    """
    p = urlparse(url).path
    if not p.startswith("/recipes/"):
        return False
    rest = p[len("/recipes/") :]
    first = rest.split("/", 1)[0] if rest else ""
    return not bool(re.match(r"^\d+-", first))


def norm(s: Optional[str]) -> str:
    return (s or "").strip().casefold()


def name_matches(target: Optional[str], actual: str) -> bool:
    """
    Мягкое совпадение: достаточно, чтобы target был подстрокой actual (без учёта регистра).
    """
    if not target:
        return True
    return norm(target) in norm(actual)


def parse_start_page(v: Optional[str]) -> int:
    """
    start-page:
      - "base" или "0" -> 0 (базовая страница без ?page=)
      - "1" -> тоже 0 (потому что page=1 не существует)
      - "2".."N" -> N
      - None -> 0
    """
    if v is None:
        return 0
    v = v.strip().lower()
    if v in ("base", "0", ""):
        return 0
    try:
        n = int(v)
    except ValueError:
        return 0
    if n <= 1:
        return 0
    return n


# -----------------------------
# Fetcher
# -----------------------------
class Fetcher:
    def __init__(
        self,
        cache_dir: Path,
        use_cache: bool = True,
        timeout: int = 30,
        retries: int = 4,
        delay_s: float = 0.0,  # доп. задержка после каждого запроса (настраиваемая)
    ) -> None:
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout
        self.retries = retries
        self.delay_s = delay_s

        (cache_dir / "listing").mkdir(parents=True, exist_ok=True)
        (cache_dir / "recipe").mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
        )

    def get(self, url: str, kind: str) -> str:
        cache_path = url_to_cache_path(self.cache_dir, kind, url)
        if self.use_cache and cache_path.exists():
            return cache_path.read_text(encoding="utf-8", errors="replace")

        last_err: Optional[Exception] = None
        backoff = 1.0

        for attempt in range(1, self.retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout)
                r.raise_for_status()
                html = r.text

                if self.use_cache:
                    cache_path.write_text(html, encoding="utf-8", errors="ignore")

                if self.delay_s > 0:
                    time.sleep(self.delay_s)

                return html
            except Exception as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    break

        raise RuntimeError(f"GET failed: {url}") from last_err


# -----------------------------
# Listing parsing (recipes list)
# -----------------------------
def extract_recipe_urls_from_listing(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []

    for a in soup.select('a[data-testid="card-material-link"][href]'):
        href = (a.get("href") or "").strip()
        if not href.startswith("/"):
            continue
        if not is_recipe_href(href):
            continue
        urls.append(urljoin(base_url, href))

    # дедуп с сохранением порядка
    seen: Set[str] = set()
    out: List[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def add_page_param(listing_url: str, page: int) -> str:
    """
    Важно: page=1 НЕ используем.
    page=2,3,... добавляем к URL (и перетираем page, если он уже был).
    """
    if page <= 1:
        return listing_url

    u = urlparse(listing_url)
    qs = parse_qs(u.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    query = urlencode(qs, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, query, u.fragment))


def collect_recipe_urls_scroll_style(
    fetcher: Fetcher,
    base_url: str,
    listing_url: str,
    max_pages: int = 25,
    stop_after_no_new_pages: int = 2,
    page_delay_s: float = 2.0,  # задержка именно между page=2,3,4...
    *,
    category_name: str = "",
    subcategory_name: str = "",
    log_pages: bool = True,
    start_page: int = 0,  # 0 = base, 2..N = начать сразу с page=N (без базы и без предыдущих страниц)
) -> List[str]:
    """
    Логика под твой кейс “скролл”:
    - базовая страница: listing_url (без ?page=1)
    - дальше: listing_url?page=2,3,4...
    - страница page=2 может содержать и старые, и новые рецепты
      => накапливаем уникальные ссылки и останавливаемся,
      когда новые перестали появляться.
    """
    tag = f"{category_name} → {subcategory_name}".strip(" →") or listing_url

    all_urls: List[str] = []
    seen: Set[str] = set()

    def add_many(urls: List[str]) -> int:
        added = 0
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            all_urls.append(u)
            added += 1
        return added

    # Стартовая логика
    # start_page=0 -> идём с базы (как обычно)
    # start_page>=2 -> пропускаем base и page=2..start_page-1, начинаем с page=start_page
    if start_page <= 0:
        html0 = fetcher.get(listing_url, kind="listing")
        added0 = add_many(extract_recipe_urls_from_listing(html0, base_url))
        if log_pages:
            print(f"[{tag}] page=base: +{added0} (total={len(all_urls)})", flush=True)
        first_page = 2
    else:
        first_page = max(2, start_page)
        if log_pages:
            print(f"[{tag}] resume: start from page={first_page} (base and previous pages skipped)", flush=True)

    no_new_streak = 0

    for page in range(first_page, max_pages + 1):
        page_url = add_page_param(listing_url, page)

        try:
            html = fetcher.get(page_url, kind="listing")
        except Exception as e:
            if log_pages:
                print(f"[{tag}] page={page}: fetch error -> stop ({e})", flush=True)
            break

        new_cnt = add_many(extract_recipe_urls_from_listing(html, base_url))

        if log_pages:
            print(f"[{tag}] page={page}: +{new_cnt} (total={len(all_urls)})", flush=True)

        if new_cnt == 0:
            no_new_streak += 1
            if no_new_streak >= stop_after_no_new_pages:
                if log_pages:
                    print(f"[{tag}] stop: no new on {stop_after_no_new_pages} pages подряд", flush=True)
                break
        else:
            no_new_streak = 0

        if page_delay_s > 0:
            time.sleep(page_delay_s + random.random() * 0.2)

    return all_urls


# -----------------------------
# Categories traversal
# -----------------------------
def iter_subcategories(categories_json: Dict[str, Any], base_url: str) -> Iterable[Tuple[str, str, str]]:
    """
    Yield: (category_name, subcategory_name, subcategory_url)
    """
    cats = categories_json.get("categories") or []
    for cat in cats:
        cat_name = (cat.get("name") or "").strip() or "Без названия"
        subs = cat.get("subcategories") or []
        for sub in subs:
            sub_name = (sub.get("name") or "").strip() or "Без названия"
            sub_url = sub.get("url") or ""
            sub_full = urljoin(base_url, sub_url)
            yield (cat_name, sub_name, sub_full)


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--categories",
        default="data/categories_and_subcategories.json",
        help="JSON категорий (см. pipeline/parse_category.py)",
    )
    ap.add_argument("--out", default="recipes.jsonl")           # данные рецептов (по строке на рецепт)
    ap.add_argument(
        "--parsed",
        default="archive/parsed_urls.txt",
        help="Список уже обработанных URL (см. archive/README.md)",
    )
    ap.add_argument("--errors", default="archive/errors.jsonl")
    ap.add_argument("--cache-dir", default="archive/cache_html")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--retries", type=int, default=4)

    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--stop-after-no-new-pages", type=int, default=2)

    ap.add_argument("--page-delay-s", type=float, default=2.0, help="пауза между запросами page=2,3,...")
    ap.add_argument("--request-delay-s", type=float, default=0.0, help="пауза после ЛЮБОГО запроса (если надо)")
    ap.add_argument("--recipe-delay-s", type=float, default=0.0, help="пауза после парсинга каждого рецепта")

    ap.add_argument("--no-page-log", action="store_true", help="не показывать прогресс по page=2,3,...")

    # ---- RESUME controls ----
    ap.add_argument("--start-category", default=None, help="начать с категории (подстрока, без регистра)")
    ap.add_argument("--start-subcategory", default=None, help="начать с подкатегории (подстрока, без регистра)")
    ap.add_argument("--start-page", default=None, help='с какой страницы начать внутри стартовой подкатегории: base|0|2|3... (page=1 не существует)')

    args = ap.parse_args()

    categories_path = Path(args.categories)
    out_path = Path(args.out)
    parsed_path = Path(args.parsed)
    errors_path = Path(args.errors)
    cache_dir = Path(args.cache_dir)

    categories_json = read_json(categories_path)
    base_url = categories_json.get("base_url") or BASE_DEFAULT

    fetcher = Fetcher(
        cache_dir=cache_dir,
        use_cache=(not args.no_cache),
        timeout=args.timeout,
        retries=args.retries,
        delay_s=args.request_delay_s,
    )

    already_parsed = load_set(parsed_path)

    start_page = parse_start_page(args.start_page)

    # Логика: пропускаем всё до первой подкатегории, которая матчится по start-category/start-subcategory.
    # В первой совпавшей подкатегории применяем start_page. Дальше идём обычно.
    started = not (args.start_category or args.start_subcategory or args.start_page)
    start_applied = False

    if not started:
        print(
            f"RESUME enabled: start_category={args.start_category!r}, start_subcategory={args.start_subcategory!r}, start_page={start_page or 'base'}",
            flush=True,
        )

    for cat_name, sub_name, sub_url in iter_subcategories(categories_json, base_url):
        if not looks_like_listing(sub_url):
            continue

        if not started:
            if name_matches(args.start_category, cat_name) and name_matches(args.start_subcategory, sub_name):
                started = True
                start_applied = True
                print(f"RESUME starting at: {cat_name} → {sub_name}", flush=True)
            else:
                continue

        # применяем start_page только один раз — на первой “стартовой” подкатегории
        sp = start_page if start_applied else 0
        start_applied = False

        # 1) Собираем ссылки на рецепты из подкатегории (через ?page=2..)
        try:
            recipe_urls = collect_recipe_urls_scroll_style(
                fetcher=fetcher,
                base_url=base_url,
                listing_url=sub_url,
                max_pages=args.max_pages,
                stop_after_no_new_pages=args.stop_after_no_new_pages,
                page_delay_s=args.page_delay_s,
                category_name=cat_name,
                subcategory_name=sub_name,
                log_pages=(not args.no_page_log),
                start_page=sp,
            )
        except Exception as e:
            append_line(
                errors_path,
                json.dumps(
                    {"stage": "collect_listing", "subcategory_url": sub_url, "error": str(e)},
                    ensure_ascii=False,
                ),
            )
            continue

        # 2) Парсим каждый рецепт (как раньше через parse_html.py)
        for recipe_url in recipe_urls:
            if recipe_url in already_parsed:
                continue

            try:
                html = fetcher.get(recipe_url, kind="recipe")
                data = parse_html.parse_recipe_html(recipe_url, html)

                rec = asdict(data)
                rec["category"] = cat_name
                rec["subcategory"] = sub_name
                rec["subcategory_url"] = sub_url

                append_line(out_path, json.dumps(rec, ensure_ascii=False))
                append_line(parsed_path, recipe_url)
                already_parsed.add(recipe_url)

                if args.recipe_delay_s > 0:
                    time.sleep(args.recipe_delay_s)

            except Exception as e:
                append_line(
                    errors_path,
                    json.dumps({"stage": "parse_recipe", "url": recipe_url, "error": str(e)}, ensure_ascii=False),
                )
                continue


if __name__ == "__main__":
    main()
