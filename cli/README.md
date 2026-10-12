# surp-cli

Official command-line client for [surp.ivc.lol](https://surp.ivc.lol) — an
OpenAI-compatible AI inference router with live cheapest-model routing.

Zero dependencies (Python 3.9+ stdlib only).

```bash
pip install surp-cli
```

## Usage

```bash
# List available routes and their live resolved models (no auth needed)
surp models

# Compare live Surp prices against other providers
surp prices --query gpt

# Gateway + upstream health
surp status

# Create a self-serve free-tier API key (no signup, no sales call)
surp key free --label sandbox

# Check a prepaid key's balance
surp balance --key sk-surp-...

# Chat — free tier needs no key
surp chat -m surp/free -p "Say hello in one sentence."

# Chat — paid routes use a prepaid key
surp chat -m surp/value -p "Explain x402 in two sentences." --key sk-surp-...

# Non-interactive stdin
echo "translate to french: hello" | surp chat -m surp/free
```

Options:

- `--base-url URL` (or `SURP_BASE_URL` env var) — default `https://surp.ivc.lol`
- `--json` — print raw JSON responses instead of formatted text

## Auth

Two paths, both scriptable: self-serve prepaid Bearer keys
(<https://surp.ivc.lol/app>) or per-request x402 USDC-on-Base payment
(<https://surp.ivc.lol/auth.md>). The `surp/free` route is sponsored and needs
no credentials within the daily cap.

## Publishing

```bash
cd cli
python -m build
twine upload dist/surp-cli-*
```
