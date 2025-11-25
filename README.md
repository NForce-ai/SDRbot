# SDRBOT - AI RevOps & Sales Development Agent

**sdrbot** is an advanced CLI agent built for Revenue Operations (RevOps) and Sales Development Representatives (SDRs). Unlike rigid automation scripts, `sdrbot` uses **Dynamic Discovery** to explore your unique CRM schema, ensuring it works with your custom objects and fields without hardcoded configuration.

It is built on top of [LangChain](https://langchain.com) and [DeepAgents](https://github.com/langchain-ai/deepagents), capable of planning multi-step workflows, researching prospects, and managing data across multiple CRMs.

---

## ⚡ Key Capabilities

### 1. Multi-CRM Support (Dynamic Discovery)
`sdrbot` doesn't guess your schema; it learns it.
- **Salesforce:** Full support for SOQL, Object Search, and CRUD on Standard & Custom Objects.
- **HubSpot:** Support for Contacts, Companies, Deals, and Custom Objects via the v3 API.
- **Attio:** Next-gen CRM support using the Attio v2 API (Objects & Attributes).

### 2. Prospecting & Enrichment
- **Lusha Integration:** Find prospects by role/industry and enrich them with B2B emails and phone numbers.
- **Web Research (Tavily):** "Google" prospects to find recent news, revenue data, or strategic insights before reaching out.

### 3. Safety & Human-in-the-Loop
- **Safe Mode:** The agent MUST ask for permission before creating, updating, or deleting records.
- **Plan Review:** For complex tasks, it writes a TODO list and asks you to review the plan before execution.

---

## 🛠️ Supported Services

| Service | Auth Method | Capabilities |
| :--- | :--- | :--- |
| **Salesforce** | OAuth 2.0 (Localhost) | SOQL, CRUD, Schema Discovery |
| **HubSpot** | OAuth 2.0 OR PAT | Search, CRUD, Schema Discovery |
| **Attio** | API Key | Search, CRUD, Attribute Discovery |
| **Lusha** | API Key | Prospecting, Person/Company Enrichment |
| **Tavily** | API Key | General Web Search, News Retrieval |

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
- **HubSpot:** `HUBSPOT_ACCESS_TOKEN` (Private App Token) **OR** `HUBSPOT_CLIENT_ID` and `HUBSPOT_CLIENT_SECRET` (OAuth)
- **Attio:** `ATTIO_API_KEY`
- **Lusha:** `LUSHA_API_KEY`

---

## 🎮 Usage

Start the agent:

```bash
sdrbot
```

### Authentication Flows
- **Salesforce:** The first time you ask for Salesforce data, the bot will open a browser for you to log in. It saves the token securely in your system keyring.
- **HubSpot (OAuth):** Similar to Salesforce, it will launch a browser flow if you are not using a Personal Access Token (PAT).
- **Attio / Lusha:** Uses the API Keys defined in your `.env`.

### Example Prompts

**1. The "Researcher" Workflow**
> "Find the VP of Sales at 'Datadog' using Lusha. Get their email, and then research recent news about Datadog using the web. Summarize the news and their contact info for me."

**2. The "RevOps" Workflow (Salesforce)**
> "I need to fix some data. Find all Leads in Salesforce created today that are missing a 'Country'. Update them to 'USA' if their phone number starts with +1."

**3. The "Cross-Platform" Workflow**
> "Find the contact 'Elon Musk' in HubSpot. If he exists, create a corresponding record in Attio in the 'People' object."

---

## 🛡️ Architecture

`sdrbot` is an implementation of the **DeepAgents** architecture:
- **Planner:** Breaks down vague requests ("Fix the data") into executable steps.
- **Tool Use:** Uses LangChain tools to interact with external APIs.
- **Memory:** Remembers context across the conversation.
- **Sandboxing:** Capable of running code locally or in remote sandboxes (Modal/Daytona) if configured.

## 🤝 Contributing



We welcome contributions! If you're interested in helping build the future of AI SDRs:



- **Code:** Check out our repository at [github.com/Revhackers/SDRbot](https://github.com/Revhackers/SDRbot)

- **Website:** Visit us at [sdr.bot](https://sdr.bot)

- **Community:** Join our [Discord](https://discord.gg/6cHN2pyzpe)





## License

[MIT](LICENSE)
