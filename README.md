# SDRBOT - AI RevOps & Sales Development Agent

**Maintained by [NForce.ai](https://nforce.ai)**

[SDRBot](https://sdr.bot) is an advanced CLI agent built for Revenue Operations (RevOps) and Sales Development Representatives (SDRs). It is an open-source project by [NForce.ai](https://nforce.ai), dedicated to empowering these teams with intelligent automation. It uses **Schema Sync** to generate strongly-typed tools that match your exact CRM schema, ensuring reliable operations with your custom objects and fields.

It is built on top of [LangChain](https://langchain.com) and [DeepAgents](https://github.com/langchain-ai/deepagents), capable of planning multi-step workflows, researching prospects, and managing data across multiple CRMs.

## ⚠️ Disclaimer

**SDRbot is provided "as is", without warranty of any kind.**

By using this software, you acknowledge that:
1.  **You are responsible for your data:** SDRbot is a powerful tool capable of creating, updating, and deleting records in your CRM. We are not liable for any data loss, corruption, or unintended modifications.
2.  **Review Plans Carefully:** Always review the agent's proposed plan before approving execution.
3.  **Third-Party Terms:** You are responsible for ensuring your use of this tool complies with the Terms of Service of any third-party platforms it interacts with.

---

## ⚡ Key Capabilities

### 1. Multi-CRM Support (Schema Sync)
`sdrbot` syncs with your CRM to generate tools with exact field names and types.
- **Salesforce:** Full support for SOQL, SOSL, and CRUD on Standard & Custom Objects.
- **HubSpot:** Support for Contacts, Companies, Deals, and Custom Objects via the v3 API.
- **Zoho CRM:** Full support for all modules including custom modules, COQL queries, and lead conversion.
- **Pipedrive:** Full support for Deals, Persons, Organizations, Products, Activities, and Leads via the v1 API.
- **Attio:** Next-gen CRM support using the Attio v2 API (Objects & Attributes).

### 2. Prospecting & Enrichment
- **Web Search:** Native web search capability for basic web searching and investigation.
- **Apollo.io Integration:** Search 210M+ contacts, enrich people and companies with emails, phone numbers, and firmographic data.
- **Lusha Integration:** Find prospects by role/industry and enrich them with B2B emails and phone numbers.
- **Hunter.io Integration:** Find and verify email addresses for any domain.
- **Tavily:** AI-powered research that can find recent news, revenue data, or strategic insights before reaching out.

### 3. Safety & Human-in-the-Loop
- **Safe Mode:** The agent MUST ask for permission before creating, updating, or deleting records.
- **Plan Review:** For complex tasks, it writes a TODO list and asks you to review the plan before execution.

---

## 🛠️ Supported Services

| Service | Auth Method | Sync Required | Capabilities |
| :--- | :--- | :---: | :--- |
| **Salesforce** | OAuth 2.0 | ✓ | SOQL, SOSL, CRUD on all objects |
| **HubSpot** | OAuth 2.0 or PAT | ✓ | Search, CRUD, Pipelines, Associations |
| **Zoho CRM** | OAuth 2.0 | ✓ | COQL, CRUD, Lead Conversion, Notes |
| **Pipedrive** | API Token or OAuth | ✓ | Search, CRUD, Pipelines, Notes, Activities |
| **Attio** | API Key | ✓ | Query, CRUD, Notes |
| **Apollo.io** | API Key | — | People/Company Search, Enrichment |
| **Lusha** | API Key | — | Prospecting, Person/Company Enrichment |
| **Hunter.io** | API Key | — | Domain Search, Email Finder, Verification |
| **PostgreSQL** | Connection String | — | SQL Queries, Table Management |
| **MySQL** | Connection String | — | SQL Queries, Table Management |
| **MongoDB** | Connection URI | — | CRUD Operations, Collection Management |
| **Tavily** | API Key | — | Web Search, News Retrieval |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Credentials for the services you wish to use.

### Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url> sdrbot
   cd sdrbot
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install the package:**
   ```bash
   pip install -e .
   ```

### Building a Standalone Executable

If you want to distribute `sdrbot` to non-technical users without requiring them to install Python, you can build a standalone executable file (e.g., `.exe` on Windows or a binary on Mac/Linux).

1. **Build the executable:**
   ```bash
   make build_executable
   ```

2. **Locate the binary:**
   The executable will be created in the `dist/` folder:
   - **Linux/Mac:** `dist/sdrbot`
   - **Windows:** `dist/sdrbot.exe`

   You can verify it works by running:
   ```bash
   ./dist/sdrbot
   ```

### Configuration

**Option 1: Interactive Setup (Recommended)**

Just run the bot! The first time you launch `sdrbot`, it will detect missing configuration and guide you through an interactive setup wizard to enter your API keys.

```bash
sdrbot
```

You can also reconfigure settings at any time using `/setup` to re-run the interactive setup wizard.

**Option 2: Manual Configuration (.env)**

If you prefer to configure it manually, copy the example environment file and fill in your keys:

```bash
cp .env.example .env
nano .env
```

**Required for Agent Brain:**
- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`)
- `TAVILY_API_KEY` (Recommended for web research)

**CRM & Tools (Fill only what you use):**
- **Salesforce:** `SF_CLIENT_ID`, `SF_CLIENT_SECRET` (Requires a Connected App)
- **HubSpot:** `HUBSPOT_ACCESS_TOKEN` (Legacy App Token) **OR** `HUBSPOT_CLIENT_ID` and `HUBSPOT_CLIENT_SECRET` (OAuth)
- **Zoho CRM:** `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REGION` (us, eu, in, au, cn, or jp)
- **Pipedrive:** `PIPEDRIVE_API_TOKEN` **OR** `PIPEDRIVE_CLIENT_ID` and `PIPEDRIVE_CLIENT_SECRET` (OAuth)
- **Attio:** `ATTIO_API_KEY`
- **Apollo.io:** `APOLLO_API_KEY`
- **Lusha:** `LUSHA_API_KEY`
- **Hunter.io:** `HUNTER_API_KEY`
- **PostgreSQL:** `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_SSL_MODE` (optional: disable, require, verify-ca, verify-full)
- **MySQL:** `MYSQL_HOST`, `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_PORT`, `MYSQL_SSL` (optional: true/false)
- **MongoDB:** `MONGODB_URI`, `MONGODB_DB`, `MONGODB_TLS` (optional: true/false)

---

## 🔐 OAuth Setup Guide

SDRbot uses OAuth 2.0 to securely connect to Salesforce, HubSpot, Zoho CRM, and Pipedrive. You'll need to create your own app credentials in each platform.

### Salesforce Connected App

Salesforce requires OAuth - there's no API key alternative.

1. **Log in to Salesforce** and go to **Setup**
2. Search for **App Manager** in the Quick Find box
3. Click **New Connected App**
4. Fill in the basic information:
   - **Connected App Name:** `SDRbot` (or any name you prefer)
   - **API Name:** `SDRbot`
   - **Contact Email:** Your email
5. Under **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**
   - **Callback URL:** `http://localhost:8080/callback/salesforce`
   - **Selected OAuth Scopes:** Add these scopes:
     - `Full access (full)`
     - Or more granular: `Manage user data via APIs (api)`, `Perform requests at any time (refresh_token, offline_access)`
6. Click **Save** (it may take 2-10 minutes to activate)
7. Go back to your Connected App and click **Manage Consumer Details**
8. Copy the **Consumer Key** → This is your `SF_CLIENT_ID`
9. Copy the **Consumer Secret** → This is your `SF_CLIENT_SECRET`

**Important:** If using a Salesforce Sandbox, set `SF_LOGIN_URL=https://test.salesforce.com` in your `.env`.

### HubSpot Authentication

HubSpot offers two options:

#### Option 1: Legacy App (Recommended)

This is the simplest method - no OAuth callback server needed.

1. **Log in to HubSpot** and go to **Settings** (gear icon)
2. Navigate to **Integrations → Legacy Apps**
3. Click **Create a legacy app**
4. Give it a name (e.g., `SDRbot`)
5. Go to the **Scopes** tab and add:
   - `crm.objects.contacts.read` / `write`
   - `crm.objects.companies.read` / `write`
   - `crm.objects.deals.read` / `write`
   - `crm.schemas.contacts.read`, `crm.schemas.companies.read`, `crm.schemas.deals.read`
   - `crm.schemas.custom.read` (for custom objects)
   - `tickets` (for ticket access)
   - `e-commerce` (for line items, products, quotes)
6. Click **Create app**
7. Copy the **Access token** → This is your `HUBSPOT_ACCESS_TOKEN`

#### Option 2: OAuth App

Use this if you need refresh tokens or plan to distribute SDRbot to others.

1. **Log in to HubSpot** and go to **Settings** (gear icon)
2. Go to developers.hubspot.com and create a developer account (or sign in to your existine one)
3. Create a new app and fill in the details
4. Go to the **Auth** tab:
   - **Redirect URL:** `http://localhost:8080/callback/hubspot`
   - Add the same scopes as above
5. Copy the **Client ID** → This is your `HUBSPOT_CLIENT_ID`
6. Copy the **Client Secret** → This is your `HUBSPOT_CLIENT_SECRET`

### Zoho CRM Self Client

Zoho CRM requires OAuth 2.0 authentication. The simplest method is creating a "Self Client" for server-side access.

1. **Log in to Zoho API Console** at [api-console.zoho.com](https://api-console.zoho.com) (use your region's domain: .eu, .in, .com.au, etc.)
2. Click **Add Client** and select **Self Client**
3. Give it a name (e.g., `SDRbot`)
4. Go to the **Client Secret** tab:
   - Copy the **Client ID** → This is your `ZOHO_CLIENT_ID`
   - Copy the **Client Secret** → This is your `ZOHO_CLIENT_SECRET`
5. **Set your region** in `.env`:
   - `ZOHO_REGION=us` for zoho.com (United States)
   - `ZOHO_REGION=eu` for zoho.eu (Europe)
   - `ZOHO_REGION=in` for zoho.in (India)
   - `ZOHO_REGION=au` for zoho.com.au (Australia)
   - `ZOHO_REGION=cn` for zoho.com.cn (China)
   - `ZOHO_REGION=jp` for zoho.jp (Japan)

**Important:** Use the API console that matches your Zoho account's data center. If your Zoho account is on zoho.eu, use api-console.zoho.eu.

### Pipedrive Authentication

Pipedrive offers two options:

#### Option 1: API Token (Simplest)

This is the easiest method - no OAuth callback server needed.

1. **Log in to Pipedrive** and go to **Settings** (gear icon)
2. Navigate to **Personal preferences → API**
3. Copy your **Personal API token** → This is your `PIPEDRIVE_API_TOKEN`

#### Option 2: OAuth App

Use this if you need refresh tokens or plan to distribute SDRbot to others.

1. **Log in to Pipedrive** as an admin
2. Go to **Settings → Tools and apps → Developer hub**
3. Click **Create an app** and select **Create private app**
4. Fill in the basic information:
   - **App name:** `SDRbot` (or any name you prefer)
5. Go to the **OAuth & access scopes** tab:
   - **Callback URL:** `http://localhost:8080/callback/pipedrive`
   - Add these scopes:
     - `deals:full` - Manage deals
     - `contacts:full` - Manage persons and organizations
     - `activities:full` - Manage activities
     - `products:full` - Manage products
     - `leads:full` - Manage leads
     - `admin` - Access pipelines, stages, users
6. Click **Save**
7. Go to the **Basic info** tab:
   - Copy the **Client ID** → This is your `PIPEDRIVE_CLIENT_ID`
   - Copy the **Client Secret** → This is your `PIPEDRIVE_CLIENT_SECRET`

---

## 🎮 Usage

Start the agent:

```bash
sdrbot
```

### Commands

| Command | Description |
|---------|-------------|
| `/help` | View the user guide with commands and shortcuts |
| `/setup` | Configure models and services |
| `/agents` | Manage agent profiles |
| `/skills` | Manage agent skills |
| `/services` | Manage CRM integrations |
| `/mcp` | Manage MCP servers |
| `/tools` | View all loaded tools (built-in, services, MCP) |
| `/sync` | Re-sync service schemas |
| `/tokens` | View token usage stats |
| `/models` | Configure LLM provider |
| `/tracing` | Configure tracing/observability |
| `/exit` | Exit SDRbot |

### Keyboard Shortcuts

| Shortcut | Description |
|----------|-------------|
| `Enter` | Submit message |
| `Ctrl+J` | New line in input |
| `Ctrl+T` | Toggle auto-approve mode |
| `Ctrl+C` | Interrupt agent |

**Note:** For copy/paste, use `Cmd+C`/`Cmd+V` on macOS or `Ctrl+Shift+C`/`Ctrl+Shift+V` on Windows/Linux.

### Auto-approve Mode

When enabled, tools run without confirmation prompts. Toggle with `Ctrl+T` or start with `--auto-approve`:

```bash
sdrbot --auto-approve
```

### Authentication Flows
- **Salesforce:** The first time you ask for Salesforce data, the bot will open a browser for you to log in. It saves the token securely in your system keyring.
- **HubSpot (OAuth):** Similar to Salesforce, it will launch a browser flow if you are not using a Personal Access Token (PAT).
- **Zoho CRM:** Opens a browser for OAuth login. Tokens are saved securely in your system keyring with automatic refresh.
- **Pipedrive:** Uses API Token directly, or launches browser OAuth flow if using Client ID/Secret. Tokens are saved securely with automatic refresh.
- **Attio / Apollo / Lusha / Hunter:** Uses the API Keys defined in your `.env`.

### Example Prompts

**1. The "Researcher" Workflow**
> "Find the VP of Sales at 'Datadog' using Lusha. Get their email, and then research recent news about Datadog using the web. Summarize the news and their contact info for me."

**2. The "RevOps" Workflow (Salesforce)**
> "I need to fix some data. Find all Leads in Salesforce created today that are missing a 'Country'. Update them to 'USA' if their phone number starts with +1."

**3. The "Cross-Platform" Workflow**
> "Find the contact 'Elon Musk' in HubSpot. If he exists, create a corresponding record in Attio in the 'People' object."

---

## 🔧 Managing Services

SDRbot uses a **service architecture** that generates strongly-typed tools based on your CRM schema. This eliminates errors like "property doesn't exist" by ensuring the agent knows exactly what fields are available.

### Setup Wizard

All service configuration is done through the interactive setup wizard:

```bash
# Run the setup wizard
/setup
```

The wizard allows you to:
- Configure and switch LLM providers (OpenAI, Anthropic, Google, Custom)
- Enable/disable services
- Configure service credentials
- View service status

### Schema Sync

For CRM services (HubSpot, Salesforce, Zoho CRM, Attio), SDRbot syncs your schema to generate strongly-typed tools.

**Automatic sync on startup**: When you launch SDRbot, if a service hasn't synced in 24 hours, it will automatically sync.

**Manual re-sync**: Use `/sync` when your CRM schema changes:

```bash
# Re-sync all enabled services
/sync

# Re-sync a specific service
/sync hubspot
```

### How Schema Sync Works

1. **Enable a service**: Use `/setup` to configure and enable a CRM service
2. **Automatic sync**: On startup, SDRbot fetches your CRM schema (objects, fields, types)
3. **Code generation**: Strongly-typed tools are generated (e.g., `hubspot_create_contact` with exact field names)
4. **Ready to use**: The agent now has tools that match your exact schema

### When to Re-sync

Run `/sync` when:
- You add new custom fields to your CRM
- You create new custom objects
- You modify field types or picklist values

Service configuration is stored in `.sdrbot/services.json` in your project directory.

---

## 🔌 MCP Server Integration

SDRbot supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), allowing you to connect to external MCP servers and use their tools directly within the agent.

### What is MCP?

MCP is a standardized protocol for AI/tool communication. Many services now offer MCP servers that expose their APIs as tools. SDRbot can connect to these servers as a client and make their tools available to the agent.

### Configuring MCP Servers

Use the MCP wizard to add, manage, and test MCP server connections:

```bash
# Open MCP configuration
/mcp
```

Or access it from the main setup wizard via `/setup` → MCP Servers.

### Supported Transports

| Transport | Description | Use Case |
|-----------|-------------|----------|
| **stdio** | Run MCP server as a subprocess | Local servers (npx, uvx, python) |
| **HTTP** | Streamable HTTP (modern) | Hosted services like Composio |
| **SSE** | Server-Sent Events (legacy) | Older MCP servers |

### Adding an MCP Server

**Example: Hosted MCP Service (HTTP)**
```
Server name: gmail
Transport: HTTP
URL: https://mcp.example.com/gmail
Authentication: API Key
API Key: your-api-key-here
```

**Example: Local MCP Server (stdio)**
```
Server name: filesystem
Transport: stdio
Command: npx
Arguments: -y @modelcontextprotocol/server-filesystem /path/to/allowed/dir
```

### Authentication Options

For HTTP/SSE servers, SDRbot supports:
- **None** - No authentication
- **Bearer Token** - `Authorization: Bearer <token>`
- **API Key** - `X-API-Key: <key>`
- **Custom Headers** - Define your own headers

Use `${VAR_NAME}` syntax to reference environment variables instead of storing secrets in plaintext.

### Auto-Recovery

If an MCP connection fails during use, SDRbot will:
1. Automatically attempt to reconnect once
2. If reconnection fails, disable the server and notify you
3. Use `/mcp` to re-enable after fixing the issue

### Configuration Storage

MCP server configuration is stored in `~/.sdrbot/mcp_servers.json`.

---

## 📊 Tracing

SDRbot integrates with popular tracing platforms to debug and monitor agent runs.

### Supported Platforms

| Platform | Description |
|----------|-------------|
| **LangSmith** | LangChain's native tracing platform |
| **Langfuse** | Open-source LLM observability (cloud or self-hosted) |
| **Opik** | Comet's LLM tracing and evaluation tool |

### Configuration

Enable tracing through the setup wizard:

```bash
/tracing
```

Or set environment variables directly:

**LangSmith:**
```bash
LANGSMITH_API_KEY=your-api-key
LANGSMITH_PROJECT=SDRbot  # optional
```

**Langfuse:**
```bash
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com  # optional, for self-hosted
```

**Opik:**
```bash
OPIK_API_KEY=your-api-key
OPIK_WORKSPACE=your-workspace  # optional
OPIK_PROJECT=SDRbot  # optional
```

When enabled, traces are automatically sent to the configured platform for every agent interaction.

---

## 🤖 Customizing the Agent

SDRbot stores agent profiles in the `./agents/` folder in your current directory. Each agent is a folder containing a prompt and memory file.

```
agents/
├── agent/           # default agent
│   ├── prompt.md    # agent instructions
│   └── memory.md    # learned preferences (persistent)
├── sales/           # custom agent for sales workflows
│   ├── prompt.md
│   └── memory.md
└── support/         # custom agent for support tasks
    ├── prompt.md
    └── memory.md
```

### Managing Agents

Use the `/agents` command to manage agent profiles directly within the app:

- **Create** new agent profiles
- **Edit** agent prompts and memory with the tabbed editor
- **Switch** between different agents
- **Delete** agents you no longer need

You can also click on the agent name in the status bar to open the agents manager.

### Starting with a Specific Agent

```bash
sdrbot --agent sales      # Uses ./agents/sales/
sdrbot --agent support    # Uses ./agents/support/
```

If the agent folder doesn't exist, it will be created with the default prompt.

### Local Data Folders

SDRbot creates these folders in your working directory (all gitignored):

| Folder | Purpose |
|--------|---------|
| `agents/` | Agent profiles (`{name}/prompt.md` + `memory.md`) |
| `skills/` | Custom skills (`{name}/SKILL.md`) - created when you add skills |
| `files/` | Agent-generated exports, reports, CSVs - created on first run |
| `generated/` | Schema-synced CRM tools (hubspot_tools.py, etc.) - created on sync |
| `.sdrbot/` | Service configuration (`services.json`) |

---

## 🧠 Agent Memory

Each agent has a **persistent memory** that survives across sessions. This allows the agent to learn your preferences, remember important context, and improve over time.

### How It Works

- **Memory file**: Each agent stores memory in `./agents/{name}/memory.md`
- **Auto-loaded**: Memory is automatically loaded into the agent's context at startup
- **No approval needed**: The agent can update its memory freely using dedicated memory tools

### Memory Tools

The agent has three tools for managing its memory (no approval required):

| Tool | Description |
|------|-------------|
| `read_memory()` | Read the current memory file |
| `write_memory(content)` | Overwrite the entire memory file |
| `append_memory(content)` | Add to the end of the memory file |

### When the Agent Updates Memory

The agent is instructed to update its memory:

- **Immediately** when you describe how it should behave or its role
- **Immediately** when you give feedback on its work
- When you explicitly ask it to remember something
- When patterns or preferences emerge during conversations

### Example Memory Content

```markdown
## Preferences
- User prefers concise responses without lengthy explanations
- Always use metric units for measurements

## Learned Patterns
- When creating HubSpot contacts, always set lifecycle_stage to "lead"
- User's company uses "ACME-" prefix for all deal names

## Project Context
- Main CRM is Salesforce, HubSpot is used for marketing only
- Q4 pipeline review happens every Friday
```

### Editing Memory Manually

You can edit an agent's memory directly:

1. Use `/agents` command
2. Select the agent
3. Switch to the **Memory** tab
4. Edit and save

Or edit the file directly at `./agents/{name}/memory.md`.

---

## 🎯 Custom Skills

Skills are reusable workflows or scripts that extend the agent's capabilities. They live in the `./skills/` folder.

### Managing Skills

Use the `/skills` command to manage skills directly within the app:

- **Create** new skills with a template
- **Edit** skill instructions with the built-in editor
- **Delete** skills you no longer need

You can also click on the skills count in the status bar to open the skills manager.

### Skill Structure

Each skill is a folder containing:
- `SKILL.md` - Instructions and description for the agent (with YAML frontmatter)
- Optional scripts, templates, or data files

Example `SKILL.md`:
```markdown
---
name: web-research
description: Structured approach to conducting thorough web research
---

# Web Research Skill

## When to Use
- User asks you to research a topic
...
```

The agent can invoke skills during conversations to perform specialized tasks.

---

## 🧪 Testing

SDRbot has a comprehensive test suite covering tool loading, CRUD operations, and service integrations.

### Running Tests

We use `make` and `uv` to manage tests.

```bash
# Run all tests (unit + integration)
make test

# Run only integration tests (requires API keys in .env)
make test_integration

# Run tests in watch mode (re-runs on file change)
make test_watch
```

Alternatively, you can run `pytest` directly via `uv`:

```bash
# Run all tests
uv run pytest tests/ -v

# Run only unit tests (fast, no API calls)
uv run pytest tests/ -v -m "not integration"

# Run only integration tests (requires API keys in .env)
uv run pytest tests/ -v -m integration

# Run tests for a specific service
uv run pytest tests/services/hubspot/ -v
```

### Test Structure

```
tests/
├── conftest.py                 # Shared fixtures
├── services/
│   ├── hubspot/
│   │   ├── test_tool_loading.py    # Tool discovery tests
│   │   ├── test_crud_operations.py # Create/search/get tests
│   │   └── test_associations.py    # Association API tests
│   ├── hunter/
│   │   └── test_hunter_tools.py    # Email finder/verifier tests
│   ├── lusha/
│   │   └── test_lusha_tools.py     # Enrichment/prospecting tests
│   ├── test_registry.py            # Service config tests
│   └── test_tool_loading.py        # get_enabled_tools tests
```

### Writing Tests

- **Unit tests** use mocked API clients and run without credentials
- **Integration tests** are marked with `@pytest.mark.integration` and require API keys
- Use the `patch_hubspot_client` fixture for mocking HubSpot API calls
- Reset cached clients with `reset_client()` before each test

---

## 🛡️ Architecture

`sdrbot` is an implementation of the **DeepAgents** architecture:
- **Planner:** Breaks down vague requests ("Fix the data") into executable steps.
- **Tool Use:** Uses LangChain tools to interact with external APIs.
- **Memory:** Remembers context across the conversation.
- **Sandboxing:** Capable of running code locally or in remote sandboxes (Modal/Daytona) if configured.

## 🤝 Contributing

We welcome contributions to SDRbot, an [NForce.ai](https://nforce.ai) project! If you're interested in helping build the future of AI SDRs:

- **Code:** Check out our repository at [github.com/Revhackers-ai/SDRbot](https://github.com/Revhackers-ai/SDRbot)
- **Website:** Visit us at [sdr.bot](https://sdr.bot)
- **Community:** Join our [Discord](https://discord.gg/XYPJe2HC9R)

## License

[MIT](LICENSE)
