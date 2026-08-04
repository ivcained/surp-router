#!/usr/bin/env python3
"""
Model knowledge base for surp.ivc.lol.

Generates unique descriptions, pros/cons, strengths, and ranking context
for every text LLM on Surplus Intelligence, keyed by model family detection.

Used by:
  - /models/<name>  individual model pages (SEO landing pages)
  - /compare        side-by-side comparison tool
  - /find           "find the right model for you" recommendation page
  - /top            top-5-per-category leaderboards
"""

from __future__ import annotations

import re
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Model families — detection rules + metadata
# Each family has: display_name, maker, description template, pros, cons,
# strengths (for the "find" tool), and known benchmark tier.
# ──────────────────────────────────────────────────────────────────────────────

FAMILIES = [
    {
        "id": "claude-opus",
        "match": ("claude-opus",),
        "name": "Claude Opus",
        "maker": "Anthropic",
        "blurb": "Anthropic's flagship frontier model. The strongest in the Claude family for complex reasoning, long-context analysis, and nuanced writing. Opus models sit at the top of most benchmark leaderboards but command premium pricing.",
        "pros": ["best-in-class reasoning and instruction following", "excellent at long-context tasks (100K+ tokens)", "strong creative and analytical writing", "high safety and refusal calibration"],
        "cons": ["most expensive tier per token", "can be overly cautious on edge-case prompts", "slower than smaller models"],
        "strengths": ["reasoning", "chat", "coding", "vision"],
        "tier": "frontier",
    },
    {
        "id": "claude-sonnet",
        "match": ("claude-sonnet",),
        "name": "Claude Sonnet",
        "maker": "Anthropic",
        "blurb": "Anthropic's balanced model — near-Opus quality at roughly half the price. Sonnet is the sweet spot for production workloads that need frontier intelligence without frontier cost.",
        "pros": ["near-frontier quality at lower cost", "fast for its capability tier", "strong coding and reasoning", "good tool-use and function calling"],
        "cons": ["not as strong as Opus on hardest tasks", "still pricier than open-source alternatives"],
        "strengths": ["reasoning", "chat", "coding"],
        "tier": "frontier",
    },
    {
        "id": "claude-haiku",
        "match": ("claude-haiku",),
        "name": "Claude Haiku",
        "maker": "Anthropic",
        "blurb": "Anthropic's fast, lightweight model. Haiku is built for speed and cost-efficiency while maintaining Claude's characteristic helpfulness and safety.",
        "pros": ["very fast response times", "low cost per token", "good quality for its size", "strong safety alignment"],
        "cons": ["weaker on complex reasoning", "not suitable for heavy coding tasks", "limited context window vs Opus/Sonnet"],
        "strengths": ["chat", "fast"],
        "tier": "standard",
    },
    {
        "id": "claude-fable",
        "match": ("claude-fable",),
        "name": "Claude Fable",
        "maker": "Anthropic",
        "blurb": "A specialized Claude variant tuned for creative writing and storytelling. Fable excels at narrative generation, character development, and long-form fiction.",
        "pros": ["exceptional creative writing", "strong character voice consistency", "good at long-form narrative"],
        "cons": ["niche specialization", "expensive", "may over-index on style over accuracy"],
        "strengths": ["chat"],
        "tier": "frontier",
    },
    {
        "id": "gpt-5",
        "match": ("gpt-5.6", "gpt-5.5", "gpt-5.4", "gpt-5.3", "gpt-5.2", "gpt-5-", "gpt-5."),
        "name": "GPT-5 Series",
        "maker": "OpenAI",
        "blurb": "OpenAI's GPT-5 family represents the latest generation of their flagship models. The series includes variants optimized for different use cases: Pro for maximum capability, standard for balanced workloads, mini/nano for speed, and codex for code generation.",
        "pros": ["top-tier reasoning and coding", "excellent tool use and agentic behavior", "strong multilingual support", "variants for every budget"],
        "cons": ["Pro variants are expensive", "can be verbose", "closed weights — no self-hosting"],
        "strengths": ["reasoning", "chat", "coding", "fast"],
        "tier": "frontier",
    },
    {
        "id": "gpt-4o",
        "match": ("gpt-4o",),
        "name": "GPT-4o",
        "maker": "OpenAI",
        "blurb": "OpenAI's multimodal workhorse — handles text, vision, and audio in a single model. GPT-4o is the reliable default for general-purpose API work.",
        "pros": ["strong all-around capability", "native multimodal (text + vision)", "fast for its tier", "widely supported by tooling"],
        "cons": ["superseded by GPT-5 series on benchmarks", "not the cheapest option", "can refuse benign prompts"],
        "strengths": ["chat", "vision", "coding"],
        "tier": "frontier",
    },
    {
        "id": "gpt-oss",
        "match": ("gpt-oss", "openai-gpt-oss"),
        "name": "GPT-OSS (Open Weights)",
        "maker": "OpenAI",
        "blurb": "OpenAI's open-weight models. GPT-OSS brings GPT-family quality to the open-source ecosystem, runnable on your own hardware and fine-tunable for specific domains.",
        "pros": ["open weights — self-hostable", "good quality-to-size ratio", "fine-tunable", "no per-token API cost if self-hosted"],
        "cons": ["requires significant GPU resources", "smaller and weaker than flagship GPT-5", "no built-in tool use in base model"],
        "strengths": ["chat", "coding"],
        "tier": "standard",
    },
    {
        "id": "gemini-pro",
        "match": ("gemini-2.5-pro", "gemini-3.1-pro", "gemini-3-pro", "gemini-pro"),
        "name": "Gemini Pro",
        "maker": "Google",
        "blurb": "Google's flagship Gemini model. Pro variants offer the largest context windows in the industry (1M+ tokens) and top-tier multimodal understanding. Excellent for document analysis, codebases, and long-context reasoning.",
        "pros": ["massive context window (1M+ tokens)", "excellent multimodal understanding", "strong reasoning and coding", "competitive pricing vs Claude/GPT"],
        "cons": ["can be inconsistent on creative tasks", "strict safety filters", "rate-limited on free tiers"],
        "strengths": ["reasoning", "vision", "coding", "chat"],
        "tier": "frontier",
    },
    {
        "id": "gemini-flash",
        "match": ("gemini-2.5-flash", "gemini-3-flash", "gemini-3-5-flash", "gemini-flash"),
        "name": "Gemini Flash",
        "maker": "Google",
        "blurb": "Google's speed-optimized Gemini variant. Flash delivers near-Pro quality at a fraction of the cost and latency. Ideal for high-volume, latency-sensitive workloads.",
        "pros": ["very fast inference", "excellent price-to-performance ratio", "large context window", "good multimodal support"],
        "cons": ["weaker than Pro on hardest tasks", "can hallucinate on complex reasoning", "limited fine-tuning options"],
        "strengths": ["fast", "chat", "vision"],
        "tier": "standard",
    },
    {
        "id": "deepseek-r1",
        "match": ("deepseek-r1",),
        "name": "DeepSeek R1",
        "maker": "DeepSeek",
        "blurb": "DeepSeek's reasoning model — an open-weight competitor to OpenAI's o-series. R1 uses extended chain-of-thought to achieve frontier-level reasoning at a fraction of the cost. Excellent for math, logic, and step-by-step problem solving.",
        "pros": ["frontier-level reasoning quality", "open weights", "exceptionally cheap for its capability", "strong math and logic"],
        "cons": ["slow — extended thinking adds latency", "verbose (shows reasoning trace)", "weaker at creative writing"],
        "strengths": ["reasoning"],
        "tier": "frontier",
    },
    {
        "id": "deepseek-v",
        "match": ("deepseek-v4", "deepseek-v3", "deepseek-3", "deepseek-4"),
        "name": "DeepSeek V-Series",
        "maker": "DeepSeek",
        "blurb": "DeepSeek's general-purpose chat models. The V-series delivers strong all-around performance at aggressive prices, making it one of the best value propositions in the LLM market.",
        "pros": ["excellent value per token", "strong coding ability", "good multilingual support", "competitive with models 5x the price"],
        "cons": ["less polished than Claude/GPT", "weaker on safety alignment", "can be verbose"],
        "strengths": ["chat", "coding", "fast"],
        "tier": "standard",
    },
    {
        "id": "llama",
        "match": ("llama-3", "llama-4"),
        "name": "Llama",
        "maker": "Meta",
        "blurb": "Meta's open-weight Llama family. Llama models are the backbone of the open-source AI ecosystem — widely deployed, heavily fine-tuned, and battle-tested in production.",
        "pros": ["open weights — fully self-hostable", "huge ecosystem of fine-tunes", "proven in production at scale", "good quality-to-size ratio"],
        "cons": ["not frontier-tier on benchmarks", "requires GPU infrastructure to self-host", "weaker tool use than proprietary models"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "qwen-coder",
        "match": ("qwen3-coder", "qwen-coder"),
        "name": "Qwen Coder",
        "maker": "Alibaba",
        "blurb": "Alibaba's coding-specialized Qwen model. The Coder variants are purpose-built for software engineering — code generation, completion, debugging, and refactoring. Consistently top of coding benchmarks among open-weight models.",
        "pros": ["top-tier coding ability", "open weights", "supports many programming languages", "excellent value"],
        "cons": ["weaker at general chat/creative", "can over-generate code comments", "limited tool use outside coding"],
        "strengths": ["coding"],
        "tier": "frontier",
    },
    {
        "id": "qwen-general",
        "match": ("qwen3-", "qwen3.", "qwen-3", "qwen3.5", "qwen3.6"),
        "name": "Qwen",
        "maker": "Alibaba",
        "blurb": "Alibaba's Qwen series — a family of open-weight models ranging from small efficient variants to massive MoE architectures. Qwen models are known for strong multilingual support (especially Chinese) and competitive benchmark scores.",
        "pros": ["strong multilingual support", "open weights", "good reasoning for the price", "many size variants to choose from"],
        "cons": ["inconsistent quality across size variants", "weaker at creative English writing", "documentation mostly in Chinese"],
        "strengths": ["chat", "reasoning"],
        "tier": "standard",
    },
    {
        "id": "qwen-vl",
        "match": ("qwen3-vl", "qwen-vl"),
        "name": "Qwen VL",
        "maker": "Alibaba",
        "blurb": "Alibaba's vision-language model. Qwen VL combines strong text understanding with image comprehension — OCR, chart reading, visual reasoning, and image-based question answering.",
        "pros": ["strong vision-language understanding", "good at OCR and document parsing", "open weights", "competitive pricing"],
        "cons": ["vision adds latency", "weaker than Gemini/Claude on complex vision", "limited to image input (no video)"],
        "strengths": ["vision", "reasoning"],
        "tier": "frontier",
    },
    {
        "id": "grok",
        "match": ("grok-4", "grok-4.", "grok-code", "grok-build"),
        "name": "Grok",
        "maker": "xAI",
        "blurb": "xAI's Grok series. Known for real-time knowledge (via X/Twitter integration), irreverent personality, and strong coding ability. Grok models are positioned as less filtered alternatives to Claude and GPT.",
        "pros": ["less restrictive content filtering", "strong coding performance", "real-time knowledge base", "good humor and personality"],
        "cons": ["premium pricing", "smaller ecosystem than OpenAI/Anthropic", "can be unpredictable in tone"],
        "strengths": ["chat", "coding"],
        "tier": "frontier",
    },
    {
        "id": "glm",
        "match": ("glm-5", "glm-4", "glm-4.7", "glm-4.6", "glm-4.5"),
        "name": "GLM (ChatGLM)",
        "maker": "Zhipu AI / Z.AI",
        "blurb": "Zhipu AI's GLM (General Language Model) series. GLM models are China's leading domestically-developed LLMs, with strong bilingual (Chinese/English) support and competitive pricing. The GLM-5 series approaches frontier quality.",
        "pros": ["excellent Chinese language support", "very competitive pricing", "strong reasoning in latest versions", "good coding ability"],
        "cons": ["weaker on niche English tasks", "less ecosystem support outside China", "safety alignment differs from Western models"],
        "strengths": ["chat", "reasoning", "coding"],
        "tier": "standard",
    },
    {
        "id": "kimi",
        "match": ("kimi-k", "kimi-k2", "kimi-k3"),
        "name": "Kimi (Moonshot)",
        "maker": "Moonshot AI",
        "blurb": "Moonshot AI's Kimi series. Kimi is known for handling extremely long contexts (up to 2M tokens) and strong performance on Chinese-language tasks. The K2/K3 variants are competitive with frontier models on reasoning.",
        "pros": ["extremely long context support", "strong Chinese language ability", "good reasoning quality", "aggressive pricing"],
        "cons": ["less known outside China", "limited English documentation", "newer — less battle-tested"],
        "strengths": ["chat", "reasoning", "coding"],
        "tier": "frontier",
    },
    {
        "id": "minimax",
        "match": ("minimax-m", "minimax"),
        "name": "MiniMax",
        "maker": "MiniMax",
        "blurb": "MiniMax's text model series. MiniMax models offer strong multilingual support and competitive pricing, with the M2/M3 series approaching frontier quality on benchmarks.",
        "pros": ["good multilingual support", "competitive pricing", "strong on benchmarks for its tier", "available in both thinking and non-thinking variants"],
        "cons": ["less ecosystem support", "limited documentation in English", "newer model family"],
        "strengths": ["chat", "reasoning"],
        "tier": "standard",
    },
    {
        "id": "mistral",
        "match": ("mistral-", "mistral-large", "mistral-small", "mistral-medium", "magistral"),
        "name": "Mistral / Magistral",
        "maker": "Mistral AI",
        "blurb": "Mistral AI's model family. Mistral pioneered the efficient small-model approach with Mixtral MoE. The Large and Small variants cover enterprise and edge use cases respectively. Magistral adds reasoning capabilities.",
        "pros": ["efficient architecture (MoE)", "open weights on some variants", "strong European language support", "good function calling"],
        "cons": ["not frontier-tier on latest benchmarks", "smaller than competitors", "can struggle with very long contexts"],
        "strengths": ["chat", "fast"],
        "tier": "standard",
    },
    {
        "id": "gemma",
        "match": ("gemma-", "gemma3", "gemma4"),
        "name": "Gemma",
        "maker": "Google",
        "blurb": "Google's open-weight model family. Gemma is the lightweight cousin of Gemini — distilled from the same research, available in sizes from 2B to 31B parameters, and fully open for commercial use.",
        "pros": ["fully open for commercial use", "small and fast", "runs on consumer GPUs", "good quality for its size"],
        "cons": ["not competitive with frontier models", "limited context window", "weaker reasoning and coding"],
        "strengths": ["chat", "fast"],
        "tier": "standard",
    },
    {
        "id": "nemotron",
        "match": ("nemotron", "nvidia-nemotron"),
        "name": "Nemotron",
        "maker": "NVIDIA",
        "blurb": "NVIDIA's Nemotron series. Built on NVIDIA's expertise in AI infrastructure, Nemotron models are optimized for inference efficiency and available across NVIDIA's cloud and enterprise platforms.",
        "pros": ["optimized for NVIDIA hardware", "efficient inference", "good for enterprise deployment", "open weights"],
        "cons": ["not frontier quality", "limited community fine-tunes", "best used on NVIDIA infrastructure"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "hermes",
        "match": ("hermes-3", "hermes-"),
        "name": "Hermes",
        "maker": "Nous Research",
        "blurb": "Nous Research's Hermes series. Hermes models are fine-tunes known for reduced censorship, strong instruction following, and excellent creative writing. Popular in the uncensored/open AI community.",
        "pros": ["minimal content restrictions", "excellent creative writing", "strong instruction following", "open weights"],
        "cons": ["less safety-aligned than commercial models", "not frontier-tier on benchmarks", "niche audience"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "mercury",
        "match": ("mercury",),
        "name": "Mercury",
        "maker": "Inception Labs",
        "blurb": "Mercury is a diffusion-based language model — a novel approach that generates text using diffusion rather than autoregression. Early results show competitive quality with potentially faster inference.",
        "pros": ["novel diffusion-based architecture", "potentially faster inference", "interesting research direction"],
        "cons": ["experimental — unproven at scale", "limited ecosystem support", "newer model with less community testing"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "trinity",
        "match": ("trinity-",),
        "name": "Trinity",
        "maker": "Arcee AI",
        "blurb": "Arcee AI's Trinity model. Trinity is designed as a balanced model with thinking/reasoning capabilities, targeting the mid-market between open-source and frontier models.",
        "pros": ["includes thinking/reasoning mode", "balanced quality", "good value", "open weights"],
        "cons": ["newer model family", "less ecosystem support", "unproven at production scale"],
        "strengths": ["reasoning", "chat"],
        "tier": "standard",
    },
    {
        "id": "venice-uncensored",
        "match": ("venice-uncensored",),
        "name": "Venice (Uncensored)",
        "maker": "Venice AI",
        "blurb": "Venice AI's uncensored model variants. These models are configured for maximum creative freedom with minimal content filtering, popular for roleplay, creative writing, and use cases where safety filters are counterproductive.",
        "pros": ["minimal content restrictions", "good for creative/roleplay use cases", "privacy-focused", "variety of specialized variants"],
        "cons": ["no safety guardrails", "not suitable for enterprise/compliance", "quality varies by variant"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "e2ee",
        "match": ("e2ee-",),
        "name": "E2EE (End-to-End Encrypted)",
        "maker": "Venice AI",
        "blurb": "End-to-end encrypted model variants. These models run with full encryption guarantees — neither the provider nor any intermediary can see your prompts or responses.",
        "pros": ["full privacy — no logging", "encrypted inference", "good for sensitive use cases", "uncensored variants available"],
        "cons": ["slower due to encryption overhead", "limited features (no streaming, no tool use)", "higher cost"],
        "strengths": ["chat"],
        "tier": "standard",
    },
    {
        "id": "aion",
        "match": ("aion-labs",),
        "name": "AION",
        "maker": "Aion Labs",
        "blurb": "Aion Labs' model. A newer entrant in the LLM space, positioning itself as a balanced model for general-purpose use.",
        "pros": ["competitive pricing", "general-purpose capability"],
        "cons": ["newer model — limited track record", "less ecosystem support"],
        "strengths": ["chat"],
        "tier": "standard",
    },
]

# Default for unknown models
DEFAULT_FAMILY = {
    "id": "unknown",
    "name": "Independent",
    "maker": "Independent",
    "blurb": "A model available on the Surplus Intelligence marketplace. Pricing and capability information is sourced from live market data.",
    "pros": ["available at competitive marketplace pricing", "accessible via surp.ivc.lol's combo routing"],
    "cons": ["limited public information available"],
    "strengths": ["chat"],
    "tier": "standard",
}


def _detect_family(model_name: str) -> dict:
    """Detect which family a model belongs to."""
    name_lower = model_name.lower()
    for fam in FAMILIES:
        for token in fam["match"]:
            if token in name_lower:
                return fam
    return DEFAULT_FAMILY


def model_info(model_name: str, price_per_1m: float = 0, sellers: int = 0,
               model_class: str = "", is_pro: bool = False) -> dict:
    """Generate complete info for a model page."""
    fam = _detect_family(model_name)
    return {
        "model": model_name,
        "family_id": fam["id"],
        "family_name": fam["name"],
        "maker": fam["maker"],
        "description": fam["blurb"],
        "pros": fam["pros"],
        "cons": fam["cons"],
        "strengths": fam["strengths"],
        "tier": "frontier" if is_pro else fam["tier"],
        "usd_per_1m": price_per_1m,
        "sellers": sellers,
        "class": model_class,
        "slug": re.sub(r'[^a-z0-9]+', '-', model_name.lower()).strip('-'),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Task recommendations for the "find" page
# ──────────────────────────────────────────────────────────────────────────────

USE_CASES = [
    {
        "id": "coding-daily",
        "label": "Everyday coding (PRs, debugging, features)",
        "icon": "💻",
        "best_classes": ["coding"],
        "prefer_tier": "any",
        "max_price": 2.0,
        "description": "You write code daily and need a reliable coding assistant that won't break the bank. You want something that's good at reading code, writing functions, and debugging — without paying frontier prices for every autocomplete.",
    },
    {
        "id": "coding-hard",
        "label": "Hard architecture & complex refactors",
        "icon": "🏗️",
        "best_classes": ["coding"],
        "prefer_tier": "frontier",
        "max_price": 10.0,
        "description": "You're tackling difficult engineering problems — system design, multi-file refactors, architecture decisions. You need the smartest coding model available, and you're willing to pay more per request for it.",
    },
    {
        "id": "chat-general",
        "label": "General questions & writing",
        "icon": "💬",
        "best_classes": ["chat"],
        "prefer_tier": "any",
        "max_price": 1.0,
        "description": "You want a smart assistant for everyday questions, drafting emails, summarizing articles, and general chit-chat. Quality matters but you don't need frontier-tier reasoning for most of this.",
    },
    {
        "id": "reasoning-math",
        "label": "Math, logic & step-by-step reasoning",
        "icon": "🧮",
        "best_classes": ["reasoning"],
        "prefer_tier": "any",
        "max_price": 5.0,
        "description": "You need a model that thinks through problems step by step — math proofs, logical analysis, multi-step planning. Reasoning models use extended chain-of-thought to get harder problems right.",
    },
    {
        "id": "fast-cheap",
        "label": "Maximum savings (high volume, simple tasks)",
        "icon": "⚡",
        "best_classes": ["fast", "chat"],
        "prefer_tier": "any",
        "max_price": 0.5,
        "description": "You're running high-volume requests — classification, extraction, simple completions, batch processing. You need the cheapest possible model that still gives quality output. Every cent per million tokens matters.",
    },
    {
        "id": "vision",
        "label": "Image understanding & visual reasoning",
        "icon": "👁️",
        "best_classes": ["vision"],
        "prefer_tier": "any",
        "max_price": 5.0,
        "description": "You need a model that can see — analyze images, read charts, do OCR, understand screenshots. Vision models combine text and image understanding for document processing and visual QA.",
    },
    {
        "id": "frontier-best",
        "label": "Best of the best (cost is no object)",
        "icon": "👑",
        "best_classes": ["chat", "coding", "reasoning"],
        "prefer_tier": "frontier",
        "max_price": 999,
        "description": "You want the absolute best model available, period. You're doing research, complex analysis, or agentic workflows where quality is the only metric that matters.",
    },
]


def recommend_models(markets: list, use_case_id: str, limit: int = 5) -> list:
    """Recommend models for a use case from live market data."""
    uc = next((u for u in USE_CASES if u["id"] == use_case_id), USE_CASES[0])
    candidates = []
    for m in markets:
        from combo_resolver import is_text_llm, usd_per_1m, class_of, is_pro, price_of
        if not is_text_llm(m):
            continue
        price = usd_per_1m(m)
        if price > uc["max_price"]:
            continue
        cls = class_of(m)
        if uc["best_classes"] and cls not in uc["best_classes"]:
            continue
        if uc["prefer_tier"] == "frontier" and not is_pro(m):
            continue
        info = model_info(m["model"], price, m.get("num_sellers") or 0, cls, is_pro(m))
        info["atomic_price"] = price_of(m)
        candidates.append(info)
    candidates.sort(key=lambda x: x["usd_per_1m"])
    return candidates[:limit]
