# Событийное меню (event recommendations)

Рекомендации блюд под типовое мероприятие: день рождения, новый год, пикник и т.д. Включается, если в тексте запроса распознан профиль события и не выключено конфигурацией.

## Поток

1. **Извлечение профиля** — [`extract_event_profile`](../app/orchestrator/event_extractor.py): ключевые слова по типу события, число гостей (ограничено сверху), роли блюд (`meal_roles`).
2. **Интент** — [`IntentRouter`](../app/orchestrator/intent_router.py): `intent="event_recommendation"`, `route="event_menu_recommendation"` при успешном профиле и `EVENT_RECOMMENDATION_ENABLED=true`.
3. **Поисковый запрос** — [`build_event_search_query`](../app/services/event_search_query.py): текст пользователя + усиление из [`EVENT_SEARCH_BOOST`](../app/services/event_profiles.py).
4. **Ранжирование** — [`EventRanker`](../app/services/event_ranker.py): скоринг кандидатов под профиль (поля вроде `event_score`, `event_roles` в строках рецептов).
5. **Сборка меню** — [`MenuComposer.compose`](../app/services/menu_composer.py): группы по ролям (`EventMenuGroup`), fallback на топ по `event_score`, если по ролям пусто.

Ответ API: поля `event_profile`, `event_menu` в [`ChatResponse`](../app/schemas/chat.py); текст ответа может проходить через [`AnswerGenerator`](../app/services/answer_generator.py) как для других сценариев.

## Переменные окружения

Задаются в [`Settings.from_env`](../app/core/config.py):

| Переменная | Смысл |
|------------|--------|
| `EVENT_RECOMMENDATION_ENABLED` | Включить ветку событийного меню (`true` по умолчанию). |
| `EVENT_CANDIDATE_MULTIPLIER` | Множитель объёма кандидатов поиска относительно `top_k`. |
| `EVENT_MIN_CANDIDATES` | Минимальное число кандидатов для отбора. |
| `EVENT_MAX_GUESTS` | Верхняя граница числа гостей из текста (согласовано с парсером профиля). |

Подробнее об общей архитектуре — [architecture.md](architecture.md).
