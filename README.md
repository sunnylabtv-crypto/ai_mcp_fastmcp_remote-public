# MCP Remote Server — HTTP-Streamable / Resumable (FastMCP)

A production-style **remote MCP (Model Context Protocol) server** built with **FastMCP**, exposing tools over a **multi-user, HTTP-streamable (resumable)** transport and deployed to the cloud via CI/CD. It integrates **Gmail, OpenAI, and Salesforce** behind a clean service layer, with **JWT-based Salesforce auth**.

> Part of the **SunnyLab** build series — the step that took a local MCP server to a resumable, multi-user remote server on cloud. Sanitized public showcase: all secrets, keys, and infra identifiers were removed; configure your own `.env` / CI secrets.

## What it demonstrates
- **Remote MCP over HTTP-streamable, resumable transport** (multi-user, not just local stdio)
- **FastMCP** server exposing tools/services
- **Enterprise integrations** — Gmail, OpenAI, Salesforce (JWT bearer flow; keys loaded from env/secret-mounted files at runtime, never committed)
- **Cloud-native delivery** — Docker, Cloud Build, GitHub Actions (all secrets via `${{ secrets.* }}`; project/VM are placeholders)
- Log retention cron + a lightweight dashboard

## Architecture
```
MCP clients (multi-user)
        │  HTTP-streamable / resumable MCP
        ▼
FastMCP remote server
   ├─ tools (gmail / openai / salesforce)
   └─ service layer  ──►  Gmail · OpenAI · Salesforce (JWT)
        │
        ▼
  deployed on cloud VM (Docker), CI/CD via GitHub Actions
```
See [`mcp_server/`](mcp_server/) for tools and services.

## Tech stack
Python · MCP / FastMCP · HTTP-streamable resumable transport · Gmail/OpenAI/Salesforce integrations · JWT · Docker · Google Cloud Build · GitHub Actions

## Project structure
```
mcp_server/      # FastMCP server, tools, services, config
generate_token.py# OAuth token helper (no secrets committed)
retention_cron.py# log retention job
dashboard.py     # lightweight dashboard
.github/         # CI/CD (secrets via ${{ secrets.* }}, placeholders for project/VM)
Dockerfile · docker-compose.yml · cloudbuild.yaml
.env.example     # required env vars (no real keys)
```

## Setup
```bash
cp .env.example .env      # your own keys; SF JWT key path, OPENAI, Google …
pip install -r requirements.txt
# run the FastMCP server (see mcp_server/)
```

## Note
Public **portfolio showcase**. Credential files (`github-deploy-key.json`, SF private key, tokens), `.env`, and infrastructure identifiers were removed before publishing. The code loads all secrets from environment / mounted files at runtime — none are committed.

---
**SunnyLab** — building agentic AI in public · Medium [@sunnylabtv](https://medium.com/@sunnylabtv) · YouTube [@sunnylabtv](https://www.youtube.com/@sunnylabtv)