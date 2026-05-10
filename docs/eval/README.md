# Parser evaluation artifacts

Store outputs from `scripts/eval/run_query_parser_eval.py` here when comparing rules vs `LLM_QUERY_PARSER_PROVIDER=peft_http` (see [model-integration.md](../model-integration.md)).

Example:

```bash
set QUERY_PARSER_MODE=rules
python scripts/eval/run_query_parser_eval.py --output docs/eval/parser_rules.json

set QUERY_PARSER_MODE=llm
set LLM_QUERY_PARSER_ENABLED=true
set LLM_QUERY_PARSER_PROVIDER=peft_http
set LLM_QUERY_PARSER_BASE_URL=http://localhost:8010
python scripts/eval/run_query_parser_eval.py --output docs/eval/parser_peft.json
```
