# sdrbot Context for Gemini

## Project Overview
**sdrbot** is an AI-powered CLI agent designed for Revenue Operations (RevOps) and Sales Development Representatives (SDRs). It leverages **Dynamic Discovery** to explore CRM schemas (Salesforce, HubSpot, Attio) without hardcoded configurations.

## Architecture
The project is built on **DeepAgents** and **LangChain**.
- **Agent Core:** Defined in `sdrbot_cli/agent.py`. It uses `create_deep_agent` to initialize the agent with tools, memory, and middleware.
- **Middleware:** Custom middleware for memory (`AgentMemoryMiddleware`), skills (`SkillsMiddleware`), and shell access (`ShellMiddleware`).
- **Skills (Tools):** Located in `sdrbot_cli/skills/`. Each CRM/service has its own subdirectory (e.g., `salesforce`, `hubspot`, `attio`, `lusha`) containing tool definitions.
- **Authentication:** Handled in `sdrbot_cli/auth/`.
- **Configuration:** Managed via `sdrbot_cli/config.py` using `python-dotenv`.

## Key Directories
- `sdrbot_cli/`: Main package source code.
  - `agent.py`: Agent graph construction and configuration.
  - `main.py`: CLI entry point.
  - `skills/`: Tool implementations for various integrations.
  - `auth/`: Authentication logic for CRMs.
  - `integrations/`: Sandbox and external service integrations.
- `tests/`: Test suite (assumed, based on `pyproject.toml`).

## Development Guidelines
- **Build System:** Uses `hatchling`.
- **Linting & Formatting:** Uses `ruff`. Configuration is in `pyproject.toml`.
  - Run linting: `ruff check .`
  - Run formatting: `ruff format .`
- **Testing:** Uses `pytest`.
  - Run tests: `pytest`
- **Execution:**
  - Run locally: `sdrbot` (if installed) or `python -m sdrbot_cli`
  - Ensure `.env` is configured with necessary API keys (OPENAI, SALESFORCE, HUBSPOT, etc.).

## Tech Stack
- **Language:** Python 3.11+
- **Frameworks:** DeepAgents, LangChain (OpenAI/Anthropic/Google), Rich (CLI UI).
- **Integrations:** Salesforce (simple-salesforce), HubSpot (hubspot-api-client), Attio, Lusha, Tavily.

## Notes
- The agent supports **Human-in-the-Loop** for sensitive operations (creating/updating records, shell commands).
- It uses a "skill" system where capabilities can be loaded dynamically.
