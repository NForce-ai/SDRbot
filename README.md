# SDRBOT - AI RevOps & Sales Development Agent

[SDRBot](https://sdr.bot) is an advanced CLI agent built for Revenue Operations (RevOps) and Sales Development Representatives (SDRs). It uses **Schema Sync** to generate strongly-typed tools that match your exact CRM schema, ensuring reliable operations with your custom objects and fields.

It is built on top of [LangChain](https://langchain.com) and [DeepAgents](https://github.com/langchain-ai/deepagents), capable of planning multi-step workflows, researching prospects, and managing data across multiple CRMs.

## ⚠️ Disclaimer

**SDRbot is provided "as is", without warranty of any kind.**

By using this software, you acknowledge that:
1.  **You are responsible for your data:** SDRbot is a powerful tool capable of creating, updating, and deleting records in your CRM. We are not liable for any data loss, corruption, or unintended modifications.
2.  **Review Plans Carefully:** Always review the agent's proposed plan before approving execution.
3.  **Third-Party Terms:** You are responsible for ensuring your use of this tool complies with the Terms of Service of any third-party platforms it interacts with (Salesforce, HubSpot, LinkedIn, etc.).

---

## ⚡ Key Capabilities

### 1. Multi-CRM Support (Schema Sync)
`sdrbot` syncs with your CRM to generate tools with exact field names and types.
- **Salesforce:** Full support for SOQL, SOSL, and CRUD on Standard & Custom Objects.
- **HubSpot:** Support for Contacts, Companies, Deals, and Custom Objects via the v3 API.
- **Attio:** Next-gen CRM support using the Attio v2 API (Objects & Attributes).

### 2. Prospecting & Enrichment
- **Lusha Integration:** Find prospects by role/industry and enrich them with B2B emails and phone numbers.
- **Hunter.io Integration:** Find and verify email addresses for any domain.
- **Web Research (Tavily):** Research prospects to find recent news, revenue data, or strategic insights before reaching out.

### 3. Safety & Human-in-the-Loop
- **Safe Mode:** The agent MUST ask for permission before creating, updating, or deleting records.
- **Plan Review:** For complex tasks, it writes a TODO list and asks you to review the plan before execution.

---

## 🛠️ Supported Services

| Service | Auth Method | Sync Required | Capabilities |
| :--- | :--- | :---: | :--- |
| **Salesforce** | OAuth 2.0 | ✓ | SOQL, SOSL, CRUD on all objects |
| **HubSpot** | OAuth 2.0 or PAT | ✓ | Search, CRUD, Pipelines, Associations |
| **Attio** | API Key | ✓ | Query, CRUD, Notes |
| **Lusha** | API Key | — | Prospecting, Person/Company Enrichment |
| **Hunter.io** | API Key | — | Domain Search, Email Finder, Verification |
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

You can also reconfigure specific settings at any time:
- `/setup`: Re-run the full setup wizard.
- `/models list`: List all available LLM providers and highlight the active one.
- `/models switch <provider>`: Switch your LLM provider (OpenAI, Anthropic, Google, Custom).
- `/models update <provider>`: Reconfigure a specific LLM provider's settings.
- `/services update <name>`: Reconfigure a specific service's credentials (e.g., `/services update salesforce`).

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
- **Attio:** `ATTIO_API_KEY`
- **Lusha:** `LUSHA_API_KEY`
- **Hunter.io:** `HUNTER_API_KEY`

---

## 🔐 OAuth Setup Guide

SDRbot uses OAuth 2.0 to securely connect to Salesforce and HubSpot. You'll need to create your own app credentials in each platform.

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

---

## 🎮 Usage

Start the agent:

```bash
sdrbot
```

### Authentication Flows
- **Salesforce:** The first time you ask for Salesforce data, the bot will open a browser for you to log in. It saves the token securely in your system keyring.
- **HubSpot (OAuth):** Similar to Salesforce, it will launch a browser flow if you are not using a Personal Access Token (PAT).
- **Attio / Lusha / Hunter:** Uses the API Keys defined in your `.env`.

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

### Service Commands

```bash
# List all services and their status
/services list

# Enable a service (auto-syncs if required)
/services enable hubspot

# Manually re-sync after schema changes
/services sync hubspot

# View detailed status
/services status hubspot

# Disable a service
/services disable hubspot
```

### How Schema Sync Works

1. **Enable a service**: Run `/services enable hubspot`
2. **Automatic sync**: SDRbot fetches your CRM schema (objects, fields, types)
3. **Code generation**: Strongly-typed tools are generated (e.g., `hubspot_create_contact` with exact field names)
4. **Ready to use**: The agent now has tools that match your exact schema

### When to Re-sync

Run `/services sync <name>` when:
- You add new custom fields to your CRM
- You create new custom objects
- You modify field types or picklist values

Service configuration is stored in `.sdrbot/services.json` in your project directory.

---

## 🤖 Customizing the Agent

SDRbot stores agent prompts in the `./agents/` folder in your current directory. This folder is created automatically on first run.

```
agents/
├── agent.md      # default agent
├── sales.md      # custom agent for sales workflows
└── support.md    # custom agent for support tasks
```

### Agent Commands

```bash
# Start with a specific agent
sdrbot --agent sales

# List all available agents
sdrbot list

# Reset an agent to the default prompt
sdrbot reset --agent agent

# Copy one agent's prompt to another
sdrbot reset --agent mybot --target sales
```

### Editing the Agent Prompt

To customize how the agent behaves, edit `./agents/agent.md`. This file controls the agent's personality, guidelines, and operational rules.

### Multiple Agents

You can create different agents for different purposes:

```bash
sdrbot --agent sales      # Uses ./agents/sales.md
sdrbot --agent support    # Uses ./agents/support.md
```

If the agent file doesn't exist, it will be created with the default prompt.

### Local Data Folders

SDRbot creates these folders in your working directory (all gitignored):

| Folder | Purpose |
|--------|---------|
| `agents/` | Agent prompt files (`{name}.md`) - created on first run |
| `skills/` | Custom skill scripts and workflows - created when you add skills |
| `files/` | Agent-generated exports, reports, CSVs - created on first run |
| `generated/` | Schema-synced CRM tools (hubspot_tools.py, etc.) - created on sync |
| `.sdrbot/` | Service configuration (`services.json`) |

---

## 🎯 Custom Skills

Skills are reusable workflows or scripts that extend the agent's capabilities. They live in the `./skills/` folder.

### Managing Skills

```bash
# List available skills
sdrbot skills list

# Create a new skill
sdrbot skills create my-workflow

# View skill details
sdrbot skills info my-workflow
```

### Skill Structure

Each skill is a folder containing:
- `skill.md` - Instructions and description for the agent
- Optional scripts, templates, or data files

The agent can invoke skills during conversations to perform specialized tasks.

---

## 🧪 Testing

SDRbot has a comprehensive test suite covering tool loading, CRUD operations, and service integrations.

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-timeout

# Run all tests
pytest tests/ -v

# Run only unit tests (fast, no API calls)
pytest tests/ -v -m "not integration"

# Run only integration tests (requires API keys in .env)
pytest tests/ -v -m integration

# Run tests for a specific service
pytest tests/services/hubspot/ -v
pytest tests/services/hunter/ -v

# Run with coverage (requires pytest-cov)
pip install pytest-cov
pytest tests/ --cov=sdrbot_cli --cov-report=term-missing
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

We welcome contributions! If you're interested in helping build the future of AI SDRs:

- **Code:** Check out our repository at [github.com/Revhackers-ai/SDRbot](https://github.com/Revhackers-ai/SDRbot)
- **Website:** Visit us at [sdr.bot](https://sdr.bot)
- **Community:** Join our [Discord](https://discord.gg/6cHN2pyzpe)

## License

[MIT](LICENSE)
