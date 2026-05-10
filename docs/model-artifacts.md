# Model artifacts (checksums)

Reference SHA256 values from the technical specification (`docs/food_helper_model_integration_tz.md`, section 2.5). Verify after download or unpack.

| File | SHA256 |
|------|--------|
| `food_helper_lora_adapter.zip` | `bce9b0a2c7622f2f5f3e38be453dc95877fdc530eaf462554769cb6add4bf21e` |
| `adapter_model.safetensors` | `c0b0c45753843d3df0f916c56a58aae9ffec851eae693b74e7eee2e94d0d27d9` |
| `adapter_config.json` | `51b3e08b3af89f9e0f05e263a9a56911c9025fe637f8dac6693fb61d173bd2b6` |
| `tokenizer.json` | `be75606093db2094d7cd20f3c2f385c212750648bd6ea4fb2bf507a6a4c55506` |

Local layout: `models/food_helper_lora_adapter/` (unpacked adapter; not committed to git).

Base model `Qwen/Qwen3-0.6B` is downloaded at runtime into the Hugging Face cache (for example Docker volume `hf_cache`).
