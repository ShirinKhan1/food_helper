# pip install beautifulsoup4 lxml requests

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


# -----------------------------
# Text utils
# -----------------------------
WS_RE = re.compile(r"\s+")
NBSP_RE = re.compile(r"[\u00A0\u202F]")  # nbsp / narrow nbsp

COMMON_ALLERGEN_HINT_1 = (
    "Здесь мы обращаем ваше внимание на то, есть ли в блюде распространенные и опасные аллергены."
)
COMMON_ALLERGEN_HINT_2 = (
    "Перед тем как готовить, убедитесь, что у вас нет индивидуальной непереносимости других продуктов из списка ингредиентов."
)


def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = NBSP_RE.sub(" ", s)
    s = WS_RE.sub(" ", s).strip()
    return s or None


def normalize_key(k: str) -> str:
    k = k.strip().rstrip(":").strip()
    k = k.rstrip("—–-").strip()
    return k


def dt_label(dt: Tag) -> Optional[str]:
    """
    Берём только прямой текст dt (без тултипов/подсказок),
    чтобы ключи вроде "Сложность" не склеивались с длинным описанием.
    """
    parts: List[str] = []
    for ch in dt.contents:
        if isinstance(ch, NavigableString):
            t = clean_text(str(ch))
            if t:
                parts.append(t)

    if parts:
        return clean_text(" ".join(parts))

    # fallback: первая строка полного текста
    t = dt.get_text("\n", strip=True)
    if not t:
        return None
    return clean_text(t.split("\n", 1)[0])


def clean_allergen_value(val: str) -> str:
    val = val.replace(COMMON_ALLERGEN_HINT_1, "").strip()
    val = val.replace(COMMON_ALLERGEN_HINT_2, "").strip()
    for cut in ("Убедитесь", "Перед тем как готовить"):
        if cut in val:
            val = val.split(cut, 1)[0].strip()
    return clean_text(val) or ""


# -----------------------------
# Models
# -----------------------------
@dataclass
class Ingredient:
    block: Optional[str]
    name: Optional[str]
    quantity: Optional[str]


@dataclass
class Step:
    position: Optional[int]
    title: Optional[str]
    text: str


@dataclass
class RecipeData:
    source: str
    recipe_url: Optional[str]                  # canonical / og:url if present
    servings: Optional[Union[int, float, str]] # recipeYield
    title: Optional[str]
    description: Optional[str]
    nutrition: Dict[str, Dict[str, Optional[str]]]
    properties: Dict[str, str]                 # includes "Аллергены" (only once), "Будет готово через", etc.
    ingredients: List[Ingredient]
    steps: List[Step]
    afterword: Optional[str]                   # "произвести впечатление" block text


# -----------------------------
# IO (optional)
# -----------------------------
def fetch_html(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


# -----------------------------
# Extractors
# -----------------------------
def extract_recipe_url(soup: BeautifulSoup) -> Optional[str]:
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        return clean_text(canonical["href"])

    ogurl = soup.find("meta", property="og:url")
    if ogurl and ogurl.get("content"):
        return clean_text(ogurl["content"])

    twurl = soup.find("meta", attrs={"name": "twitter:url"})
    if twurl and twurl.get("content"):
        return clean_text(twurl["content"])

    return None


def extract_servings(soup: BeautifulSoup) -> Optional[Union[int, float, str]]:
    ry = soup.find(attrs={"itemprop": "recipeYield"})
    if ry:
        t = clean_text(ry.get_text(" ", strip=True))
        if t:
            m = re.search(r"\d+(?:[.,]\d+)?", t.replace(" ", ""))
            if m:
                num = m.group().replace(",", ".")
                try:
                    f = float(num)
                    return int(f) if f.is_integer() else f
                except Exception:
                    return t
            return t

    inp = soup.select_one("input.yield")
    if inp and inp.get("value"):
        v = clean_text(inp["value"])
        if v:
            m = re.search(r"\d+(?:[.,]\d+)?", v)
            if m:
                num = m.group().replace(",", ".")
                try:
                    f = float(num)
                    return int(f) if f.is_integer() else f
                except Exception:
                    pass
            return v

    return None


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    h1 = soup.find("h1")
    return clean_text(h1.get_text(" ", strip=True)) if h1 else None


def extract_description(soup: BeautifulSoup) -> Optional[str]:
    d = soup.find(attrs={"itemprop": "description"})
    if d:
        t = clean_text(d.get_text(" ", strip=True))
        if t:
            return t

    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        t = clean_text(og["content"])
        if t:
            return t

    h1 = soup.find("h1")
    if h1:
        for el in h1.find_all_next(["p", "div"], limit=80):
            txt = clean_text(el.get_text(" ", strip=True))
            if txt and len(txt) >= 40:
                return txt

    return None


def extract_nutrition(soup: BeautifulSoup) -> Dict[str, Dict[str, Optional[str]]]:
    nutrition: Dict[str, Dict[str, Optional[str]]] = {}
    root = soup.find(attrs={"itemprop": "nutrition"})
    if not root:
        return nutrition

    for n in root.select("[itemprop]"):
        dt = n.find("dt")
        if not dt:
            continue
        label = clean_text(dt.get_text(" ", strip=True))
        if not label:
            continue

        value_el = n.select_one(".nutrient_value__dd48k") or n.find("dd")
        unit_el = n.select_one(".nutrient_unit__Z3znI")

        nutrition[label] = {
            "value": clean_text(value_el.get_text(" ", strip=True)) if value_el else None,
            "unit": clean_text(unit_el.get_text(" ", strip=True)) if unit_el else None,
            "itemprop": n.get("itemprop"),
        }

    serving = root.select_one(".servingSize")
    if serving:
        nutrition["Порция"] = {
            "value": clean_text(serving.get_text(" ", strip=True)),
            "unit": None,
            "itemprop": "servingSize",
        }

    return nutrition


def extract_properties(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Достаёт пары dt/dd из блока свойств.
    Важно: всё, что связано с аллергенами, нормализуем в ЕДИНСТВЕННЫЙ ключ "Аллергены".
    """
    props: Dict[str, str] = {}

    # надёжный якорь для food.ru в твоих HTML
    root = soup.select_one("[class*='properties_wrapper__']") or soup

    dts = root.select("dt[class*='properties_property__']")
    if not dts:
        dts = soup.find_all("dt")  # fallback

    for dt in dts:
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue

        key = dt_label(dt)
        val = clean_text(dd.get_text(" ", strip=True))
        if not key or not val:
            continue

        key = normalize_key(key)
        k_cf = key.casefold()

        # нормализуем аллерген в один ключ
        if k_cf in {"распространенный аллерген", "аллергены"}:
            key = "Аллергены"
            val = clean_allergen_value(val)

        if val:
            props[key] = val

    # гарантируем, что "Распространенный аллерген" не просочится
    props.pop("Распространенный аллерген", None)

    return props


def extract_ingredients(soup: BeautifulSoup) -> List[Ingredient]:
    items: List[Ingredient] = []

    for tr in soup.select('tr.ingredient[itemprop="recipeIngredient"]'):
        name_el = tr.select_one(".name")
        name = clean_text(name_el.get_text(" ", strip=True)) if name_el else None

        tds = tr.find_all("td")
        quantity = clean_text(tds[-1].get_text(" ", strip=True)) if tds else None

        block = None
        h3 = tr.find_previous("h3")
        if h3 and h3.find_parent("section", id="ingredients"):
            block = clean_text(h3.get_text(" ", strip=True))

        items.append(Ingredient(block=block, name=name, quantity=quantity))

    # дедуп
    seen = set()
    uniq: List[Ingredient] = []
    for it in items:
        key = (it.block or "", it.name or "", it.quantity or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    return uniq


def extract_steps(soup: BeautifulSoup) -> List[Step]:
    steps: List[Step] = []

    for step in soup.select('div[itemprop="recipeInstructions"][itemtype*="HowToStep"]'):
        title_el = step.find("h3")
        title = clean_text(title_el.get_text(" ", strip=True)) if title_el else None

        text_el = step.select_one('[itemprop="text"]')
        text = clean_text(text_el.get_text(" ", strip=True)) if text_el else None
        if not text:
            continue

        pos_el = step.select_one('[itemprop="position"]')
        pos_raw = pos_el.get("content") if pos_el else None
        pos = int(pos_raw) if pos_raw and str(pos_raw).isdigit() else None

        steps.append(Step(position=pos, title=title, text=text))

    if any(s.position is not None for s in steps):
        steps.sort(key=lambda x: (x.position is None, x.position or 0))

    return steps


def extract_afterword(soup: BeautifulSoup) -> Optional[str]:
    """
    На твоих страницах послесловие лежит под h3 "произвести впечатление"
    и дальше идёт текст в span[class*="markup_text"].
    """
    h3: Optional[Tag] = None
    for tag in soup.find_all("h3"):
        t = clean_text(tag.get_text(" ", strip=True))
        if t and t.casefold() == "произвести впечатление":
            h3 = tag
            break

    if not h3:
        return None

    texts: List[str] = []

    # Обычно текст сразу в следующих соседях
    for sib in h3.find_next_siblings():
        if isinstance(sib, Tag) and sib.name == "h3":
            break
        if isinstance(sib, Tag):
            for span in sib.select('span[class*="markup_text"]'):
                t = clean_text(span.get_text(" ", strip=True))
                if t:
                    texts.append(t)

    # Fallback: если структура поменялась, попробуем пройтись по descendants секции
    if not texts:
        section = h3.find_parent("section")
        if section:
            passed_h3 = False
            for el in section.descendants:
                if el is h3:
                    passed_h3 = True
                    continue
                if not passed_h3:
                    continue
                if isinstance(el, Tag) and el.name == "h3":
                    break
                if isinstance(el, Tag) and el.name == "span":
                    classes = el.get("class") or []
                    if any("markup_text" in c for c in classes):
                        t = clean_text(el.get_text(" ", strip=True))
                        if t:
                            texts.append(t)

    return clean_text(" ".join(texts))


# -----------------------------
# Parse API
# -----------------------------
def parse_recipe_html(source: str, html: str) -> RecipeData:
    soup = BeautifulSoup(html, "lxml")

    recipe_url = extract_recipe_url(soup)
    servings = extract_servings(soup)

    return RecipeData(
        source=source,
        recipe_url=recipe_url,
        servings=servings,
        title=extract_title(soup),
        description=extract_description(soup),
        nutrition=extract_nutrition(soup),
        properties=extract_properties(soup),
        ingredients=extract_ingredients(soup),
        steps=extract_steps(soup),
        afterword=extract_afterword(soup),
    )


def parse_recipe_file(path: Union[str, Path]) -> RecipeData:
    path = Path(path)
    html = path.read_text(encoding="utf-8")
    return parse_recipe_html(str(path), html)


def parse_recipe_url(url: str) -> RecipeData:
    html = fetch_html(url)
    data = parse_recipe_html(url, html)
    # если в HTML нет canonical/og:url — оставим исходный url
    if not data.recipe_url:
        data.recipe_url = url
    return data


# -----------------------------
# Example run
# -----------------------------
if __name__ == "__main__":
    files = [
        "218540-picca-na-skovorode-s-kolbasoi.html",
        "270567-oladi-iz-ovsjanyh-hlopev-i-brokkoli.html",
        "223070-kukis.html",
    ]

    all_out: List[Dict[str, Any]] = []
    for f in files:
        data = parse_recipe_file("archive/html_pages/" + f)
        all_out.append(asdict(data))

        out_json = Path(f).with_suffix(".json")
        out_json.write_text(json.dumps(asdict(data), ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            f"OK: {f} -> {out_json.name} | servings={data.servings} | "
            f"Аллергены={data.properties.get('Аллергены')} | afterword={bool(data.afterword)}"
        )

    out_all = Path("archive/recipes_all.json")
    out_all.parent.mkdir(parents=True, exist_ok=True)
    out_all.write_text(json.dumps(all_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {out_all}")
