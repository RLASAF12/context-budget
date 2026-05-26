# context-budget

> Know your token cost before you load.

A CLI tool for Claude Code users. Counts the token cost of files in your workspace so you can make informed decisions about what to load in a session — before you hit the context wall.

## The Problem

Claude Code has a ~200K token context window. Your system prompt + tools already consume ~80K. Every file you load eats into the remaining ~120K. Load too much = early compaction = shorter, less useful sessions.

But you don't know the cost until it's too late.

## The Solution

```bash
# See what's eating your context budget
python3 context_budget.py scan ./my-workspace

# Check the exact cost of files you're about to load
python3 context_budget.py check CLAUDE.md M-memory/SESSION-BRIEF.md A-agents/jams-agent.md

# Validate your tiered loading strategy (reads CLAUDE.md tier definitions)
python3 context_budget.py tier ./my-workspace
```

## Install

```bash
pip install tiktoken
# That's it — single file, no other dependencies
```

## Example Output

```
--- Token Scan Results for './M-memory' ---
Budget: 50,000 tokens | Claude Max Context: 200,000 tokens
───────────────────────────────────────────────────────────
  15,134 tokens  (30.3% budget) (7.6% window)  learning-log-archive.md
   9,080 tokens  (18.2% budget) (4.5% window)  vision-backlog.md
   2,793 tokens   (5.6% budget) (1.4% window)  decisions.md
   1,656 tokens   (3.3% budget) (0.8% window)  SESSION-BRIEF.md
───────────────────────────────────────────────────────────
Total: 40,271 tokens (80.5% of budget) — ⚠️ NEAR LIMIT
```

**Insight:** Loading `learning-log-archive.md` alone costs 7.6% of the full window. SESSION-BRIEF (0.8%) gives you 90% of the value at 10% of the cost. That's why tiered loading works.

## Commands

| Command | What it does |
|---------|-------------|
| `scan PATH` | Recursively lists all files sorted by token count |
| `check FILE1 FILE2...` | Sums up token costs for specific files |
| `tier PATH` | Reads CLAUDE.md, maps files to their loading tier |

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--budget N` | 50000 | Token budget to compare against |
| `--format json` | text | Output as JSON for scripting |

## Use Cases

- **Before a session:** Run `scan` to identify which files are most expensive
- **Planning a CLAUDE.md:** Use `check` to validate that your Tier 1 files stay under budget
- **Debugging slow sessions:** Find which files are causing context bloat
- **Tiered loading audits:** Use `tier` to confirm your loading strategy is cost-efficient

## Built by

[Harel Asaf](https://github.com/RLASAF12) · 2026-05-26
