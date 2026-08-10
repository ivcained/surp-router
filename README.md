# surp — x402-paywalled LLM gateway

> Cheapest AI inference on the internet. Pay per request in USDC on Base. No account, no API key required.

**surp** is an OpenAI-compatible LLM gateway that routes requests to the cheapest offers on the [Surplus Intelligence](https://www.surplusintelligence.ai/) marketplace and pays for them with [x402](https://x402.org/) — a micropayment protocol that turns any HTTP response into a paid one. The first request returns `402 Payment Required`; the client signs a USDC transfer and retries; the gateway verifies the signature, settles on-chain, and streams the LLM response.

## What's here

| Component | Purpose |
|---|---|
| `gateway.py` | The x402-paywalled aiohttp server. OpenAI-compatible `/v1/chat/completions` endpoint + website pages. |
| `proxy.py` | Internal resolver proxy. Calls the Surplus marketplace, resolves combos to the cheapest live model. |
| `combo_resolver.py` | 15 routing combos (best/pro × coding/reasoning/fast/vision/chat + free). |
| `cache_tech.py` | Two-layer cache: exact-response cache (0.1¢) + sticky routing (preserves KV prefix cache). |
| `reward_ledger.py` | Off-chain SRP reward tokens for cache writers, authors, and readers. |
| `free_models.py` | Treasury-sponsored free tier with daily/per-IP budgets, free API keys, conversion tracking. |
| `provider_health.py` | Per-model TPS (request RPS), p50/p95 latency, failure rate, composite health score. |
| `cache_affinity.py` | Ad-network-style prefix-hash affinity tracking for the cache auction. |
| `model_benchmarks.py` | Verified output-TPS, TTFT, and throughput-per-dollar benchmarks. |
| `benchmark_runner.py` | Live benchmark runner that streams real requests and records generation throughput. |
| `nft_gate.py` | Token-gated access prototype (bypass x402 with sufficient token balance). |
| `stats.py` | SQLite-backed usage stats with WAL mode and thread-safe writes. |

## Public pages

| Page | URL |
|---|---|
| Homepage | https://surp.ivc.lol/ |
| API docs | https://surp.ivc.lol/docs |
| Status (live) | https://surp.ivc.lol/status |
| Free models + budget | https://surp.ivc.lol/free-models |
| Verified TPS benchmarks | https://surp.ivc.lol/performance |
| Provider health board | https://surp.ivc.lol/health |
| Cache-affinity auction | https://surp.ivc.lol/auction |
| Features & updates | https://surp.ivc.lol/features |
| Compare models | https://surp.ivc.lol/compare |
| Cache-aware routing | https://surp.ivc.lol/cache |
| Reward proposal | https://surp.ivc.lol/proposal |

## Quick start

```bash
# 1. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install aiohttp aiohttp-cors eth-account eth-utils web3 x402

# 2. Configure secrets
cp .env.example .env
# Edit .env: set SURPLUS_INTELLIGENCE_API_KEY, SURP_PAY_TO, etc.

# 3. Run the resolver proxy
SURPLUS_INTELLIGENCE_API_KEY=inf_... python3 proxy.py --port 20129 &

# 4. Run the gateway
python3 gateway.py &

# 5. Make a request (no payment — free tier)
curl -X POST http://localhost:20130/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"surp/free",
       "messages":[{"role":"user","content":"Hello from surp"}],
       "max_tokens":50}'
```

## Combos

surp routes by **combo** — a named bundle of models. The gateway picks the cheapest live one:

```text
surp/best-chat         → cheapest text LLM right now
surp/best-coding       → cheapest coding model
surp/best-reasoning    → cheapest reasoning model
surp/best-fast         → cheapest fast/small model
surp/pro-chat          → pro-tier chat (better models)
surp/pro-coding        → pro-tier coding
surp/free              → treasury-sponsored free (no payment)
surp/free-coding       → free coding models
surp/free-fast         → free fast/small models
surp/direct/<model-id> → pin one specific model (for benchmarks / pinned SLAs)
```

## x402 payment flow

1. Client sends a request without payment.
2. Gateway returns `402 Payment Required` with `X-Payment` header (amount, asset, payee).
3. Client signs a USDC `transferWithAuthorization` (EIP-3009) for the amount.
4. Client retries with `X-Payment` header containing the signed payload.
5. Gateway verifies the signature via the facilitator, settles on-chain, streams the response.

No account, no API key, no prepaid balance. Each request is a separate micropayment.

## Tests

```bash
source venv/bin/activate
pytest tests/ -q
```

## Architecture

```
client → [nginx :443] → [gateway :20130] → x402 verify → resolve combo → [resolver :20129] → Surplus marketplace
                                          ↓
                                     cache check → exact-response cache (0.1¢)
                                          ↓
                                     record: stats, health, affinity, benchmark
```

## License

MIT. See [OmniRoute attribution](data/OMNIROUTE_LICENSE.txt) for the free-tier catalog intelligence integration.

## Links

- Website: https://surp.ivc.lol/
- Surplus Intelligence: https://www.surplusintelligence.ai/
- x402 protocol: https://x402.org/
- PayAI facilitator: https://facilitator.payai.network/

<!-- auto-deploy test marker -->
