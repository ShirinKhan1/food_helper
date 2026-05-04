# Архив

Сюда перенесены артефакты, которые **не нужны** текущему циклу «Postgres + pgvector + loader/embed»:

| Путь | Что это |
|------|---------|
| `embeddings.json` | Старый офлайн-дамп векторов; источник истины для векторов — таблица `recipe_embeddings` |
| `parsed_urls.txt` | Состояние парсера (какие URL уже обработаны); при новом прогоне можно указать `--parsed archive/parsed_urls.txt` |
| `errors.jsonl` | Лог ошибок парсинга |
| `recipes_all.json` | Черновой сбор из примера в `parse_html.py` |
| `cache_html/` | Кэш скачанных HTML (listing/recipe) |
| `html_pages/` | Локальные HTML для отладки `parse_html` |
| `дизайн дока.drawio` | Черновик диаграммы |

Рабочие файлы у корня: **`recipes.jsonl`** (загрузка в БД), **`data/categories_and_subcategories.json`**.
