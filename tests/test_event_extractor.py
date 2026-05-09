from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.event_extractor import extract_event_profile, extract_guests_count
from app.schemas.event import EventProfile


def test_extract_new_year_and_guests() -> None:
    p = extract_event_profile("Подбери рецепты на Новый год для 6 человек", max_guests=30)
    assert p is not None
    assert p.event_type == "new_year"
    assert p.guests_count == 6
    assert "starter" in p.meal_roles


def test_extract_date_night() -> None:
    p = extract_event_profile("Что приготовить для свидания?", max_guests=30)
    assert p is not None
    assert p.event_type == "date_night"
    assert p.guests_count is None


def test_extract_friends() -> None:
    p = extract_event_profile("Что приготовить, если друзья придут вечером?", max_guests=30)
    assert p is not None
    assert p.event_type == "friends_gathering"


def test_extract_birthday_guests() -> None:
    p = extract_event_profile("Собери меню на день рождения на 8 человек", max_guests=30)
    assert p is not None
    assert p.event_type == "birthday"
    assert p.guests_count == 8


def test_extract_picnic() -> None:
    p = extract_event_profile("Нужны блюда для пикника", max_guests=30)
    assert p is not None
    assert p.event_type == "picnic"


def test_guests_variants() -> None:
    assert extract_guests_count("нас будет 4", max_guests=30) == 4
    assert extract_guests_count("будет 5 друзей", max_guests=30) == 5
    assert extract_guests_count("для 8 гостей", max_guests=30) == 8


def test_guests_out_of_range() -> None:
    assert extract_guests_count("на 99 человек", max_guests=30) is None


def test_no_event() -> None:
    assert extract_event_profile("найди рецепты с курицей", max_guests=30) is None
