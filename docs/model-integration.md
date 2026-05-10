# Model service (PEFT LoRA)

Food Helper can use a **separate HTTP model service** that runs `Qwen/Qwen3-0.6B` with the PEFT LoRA adapter (`food_helper_decision_planner`). The main API talks to it via `LLM_QUERY_PARSER_PROVIDER=peft_http` (recommended MVP: query parser only).

## Layout

- Unpacked adapter: `models/food_helper_lora_adapter/` (see [model-artifacts.md](model-artifacts.md); directory is gitignored).
- Service code: `model_server/` (FastAPI + Transformers + PEFT).
- Image: `docker/Dockerfile.model`.

## Quick start (Docker)

1. Unpack `data/food_helper_lora_adapter.zip` into `models/food_helper_lora_adapter/` if the directory is missing.
2. Build and start database, model service, and API:

```bash
docker compose build model api
docker compose up -d db model api
```

3. First start of `model` downloads the base model from Hugging Face into the `hf_cache` volume (can take several minutes).

4. Check health:

```bash
curl -s http://localhost:8010/health | jq .
curl -s http://localhost:8000/health | jq .
```

## API environment (MVP: parser only)

Example (parser via PEFT, answers template-only):

```env
QUERY_PARSER_MODE=auto
LLM_QUERY_PARSER_ENABLED=true
LLM_QUERY_PARSER_PROVIDER=peft_http
LLM_QUERY_PARSER_MODEL=food-helper-qwen3-0.6b-lora
LLM_QUERY_PARSER_BASE_URL=http://model:8010
LLM_QUERY_PARSER_TEMPERATURE=0
LLM_QUERY_PARSER_MAX_TOKENS=700
LLM_QUERY_PARSER_NUM_CTX=4096
LLM_QUERY_PARSER_TIMEOUT_SECONDS=15
LLM_QUERY_PARSER_POSTCHECK_ENABLED=true

ANSWER_MODE=template
LLM_ENABLED=false
```

`LLM_QUERY_PARSER_BASE_URL` may be omitted; then `LLM_BASE_URL` is used (useful if both clients share one host).

## Rollback

- `QUERY_PARSER_MODE=rules` — no LLM parsing.
- `LLM_QUERY_PARSER_ENABLED=false` — disables parser LLM client.
- `ANSWER_MODE=template` and `LLM_ENABLED=false` — no LLM answers.

## Troubleshooting

| Symptom | Check |
|--------|--------|
| `model` `/health` shows `model_loaded: false` | `load_error` in JSON; adapter path mounted; disk space; PEFT/transformers versions. |
| Slow parser on CPU | Use `QUERY_PARSER_MODE=auto`; increase RAM (4–8 GB); or GPU override (not included by default). |
| API `/health` `llm.parser_health: error` | Model container up; `LLM_QUERY_PARSER_BASE_URL` reachable from `api` network; firewall. |
| Base model download fails | HF access from container; pre-fill `hf_cache` volume; proxy `HF_HOME`. |

## Related

- Full specification: [food_helper_model_integration_tz.md](food_helper_model_integration_tz.md)
