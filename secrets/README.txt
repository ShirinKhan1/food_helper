Секреты (токены и т.п.) не храните в git.

Вариант 1 (рекомендуется для docker compose): в корне репозитория создайте файл `.env`
из `.env.example` и укажите HF_TOKEN=...

Вариант 2: скопируйте secrets/huggingface.env.example в secrets/huggingface.env
и перенесите строку HF_TOKEN в корневой `.env` — compose читает переменные
подстановки из корневого `.env` автоматически.
