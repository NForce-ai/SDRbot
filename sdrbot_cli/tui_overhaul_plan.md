# Textual Overhaul Plan for SDRbot CLI

## Current UI Stack Analysis
*   **Output:** Uses `rich` directly for printing formatted text, tables, panels, and diffs to `stdout`. Logic is centralized in `sdrbot_cli/ui.py`.
*   **Input:** Uses `prompt_toolkit` for the interactive prompt, history, key bindings (e.g., `Ctrl+T`), and auto-completion. Logic is in `sdrbot_cli/input.py`.
*   **Architecture:** A procedural `while` loop in `sdrbot_cli/main.py` that blocks waiting for user input, then awaits the agent's response.

## Proposed Plan: Textual Overhaul
We will replace the procedural loop with an event-driven **Textual App**.

### New Architecture:
*   **`sdrbot_cli/tui/app.py`**: The main application class (`App`).
*   **`sdrbot_cli/tui/widgets.py`**: Custom widgets (e.g., `ChatLog`, `AgentStatus`).
*   **Worker-based Execution**: The agent will run in a background worker to keep the UI responsive during long-running tasks.

### Key Features:
*   **Full-Screen Interface**: A modern TUI with dedicated areas for chat history, input, and status.
*   **Rich Integration**: Re-use existing `rich` renderables from `ui.py` by feeding them into Textual's `RichLog` widget.
*   **Asynchronous Input**: Non-blocking input handling using Textual's event system.

### Task List:
1.  **Add `textual` to `pyproject.toml` dependencies** - **COMPLETED**
2.  **Create `sdrbot_cli/tui` package structure** - **COMPLETED**
3.  **Implement `sdrbot_cli/tui/app.py` (Main App Skeleton)** - **COMPLETED**
4.  **Implement `sdrbot_cli/tui/widgets.py` (ChatLog, InputArea)** - **COMPLETED**
5.  **Adapt `sdrbot_cli/ui.py` renderers for Textual (Output Migration)** - **COMPLETED**
6.  **Integrate Agent Execution Loop into Textual Worker** - **COMPLETED**
    *   Create `sdrbot_cli/tui/agent_worker.py` - **COMPLETED**
    *   Modify `sdrbot_cli/tui/app.py` to interact with the worker - **COMPLETED**
    *   Refactor agent execution logic to be worker-compatible - **COMPLETED**
7.  **Replace `sdrbot_cli/main.py` entry point to launch Textual App** - **COMPLETED**
8.  **CSS Styling**: Add a `sdrbot_cli/tui/sdrbot.css` file and link it to the app to define the layout and styling of the Textual widgets. - **COMPLETED**
9.  **Refine UI components**: Enhance the `RichLog` and `Input` widgets as needed, and consider creating custom widgets for specific displays (e.g., token usage, agent status). - **COMPLETED**
10. **Implement interactive approval**: Replace the current non-interactive tool approval with a proper Textual modal or input for user confirmation. - **COMPLETED**
11. **Integrate other commands**: Ensure all existing slash commands (`/setup`, `/models`, etc.) are properly integrated and displayed within the TUI. - **COMPLETED**

### Next Steps:
1.  **Testing**: Thoroughly test the Textual application to ensure all functionalities work as expected.