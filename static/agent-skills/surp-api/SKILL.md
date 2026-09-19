---
name: surp-api
description: Use Surp for OpenAI-compatible AI inference with live routing, prepaid API keys, or x402 USDC payments on Base.
---

# Surp API

Use this skill when an agent needs text inference through an OpenAI-compatible API, wants Surp to select a model by cost, speed, or quality, or needs agent-native x402 payment.

## Endpoints

- Base URL: https://surp.ivc.lol/v1
- Models: GET https://surp.ivc.lol/v1/models
- Chat: POST https://surp.ivc.lol/v1/chat/completions
- OpenAPI: https://surp.ivc.lol/openapi.json

## Authentication

Use a prepaid Bearer API key or fulfill the HTTP 402 payment challenge with a PAYMENT-SIGNATURE. Never send wallet private keys.
