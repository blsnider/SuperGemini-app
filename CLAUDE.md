# CLAUDE.md: Guide for Using Claude in Super Gemini Retail Analytics Project

## Overview
This CLAUDE.md file serves as a special configuration and guidance document for Anthropic's Claude AI model within the Super Gemini Retail Analytics project. Claude automatically ingests this file into its context when interacting with the codebase, providing project-specific instructions, constraints, and best practices. This ensures Claude behaves consistently, follows coding standards, and generates outputs aligned with the project's goals.

The Super Gemini project is a Flask-based AI-driven retail analytics tool that converts natural language queries into BigQuery SQL, performs inventory weighting, returns analysis, summarization, and visualization. Claude is primarily used for generating concise business summaries (via `summarizer.py`) and custom AI responses (via `core.py`). This file helps Claude understand the project's structure, schema, and retail domain to produce accurate, actionable insights.

**Key Principles for Claude:**
- Always prioritize truth-seeking and accuracy; avoid hallucinations by grounding responses in provided data or schema.
- Focus on retail analytics: Sales trends, inventory optimization, returns risk, and actionable recommendations.
- Keep outputs concise (<200 words for summaries), structured (use bold headers), and business-oriented.
- Do not generate or execute code that modifies the filesystem, installs packages, or accesses external resources beyond what's allowed in the REPL-like environment.

## Project Structure
- **Core Files**:
  - `app.py`: Flask entrypoint; handles routes like `/chat` and integrates weighting logic.
  - `chatbot/core.py`: Main chatbot class; manages query to SQL conversion and AI responses.
  - `chatbot/summarizer.py`: Uses Claude for generating summaries from DataFrames (e.g., inventory insights).
  - `chatbot/sql_generator.py`: Generates SQL based on intents; ensure queries respect BigQuery schema.
  - `weighting_logic.py`: Business logic for coverage analysis; Claude can assist in enhancing calculations.
- **Data Schema**: Refer to `query_patterns.py` for BigQuery tables (e.g., `fct_sales`, `dim_skus`, `mart_inventory_snapshots`). Always validate field paths (e.g., no invalid vendors).
- **AI Integration**: Claude is called via `api_clients` (in `core.py`); models like `claude-3-sonnet` are supported.

## Setup Instructions
1. **API Key**: Obtain an Anthropic API key from [anthropic.com](https://www.anthropic.com). Store it securely:
   - Local: In `.env` as `ANTHROPIC_API_KEY=your-key`.
   - Production (GCP): Use Secret Manager (integrated in `app.py` via `load_secret`).
2. **Dependencies**: Ensure `anthropic` SDK is in `requirements.txt`. No additional installs needed in REPL.
3. **Model Selection**: Set `DEFAULT_MODEL=claude-3-sonnet` in env vars or Config class for summaries.
4. **Testing**: Use `/chat` endpoint with queries like "Summarize inventory for Fargo store" to invoke Claude.

## Usage Guidelines
- **For Summaries (`summarizer.py`)**: When prompted, analyze DataFrames for retail insights. Structure output with:
  1. **Summary Paragraph**: Key findings (e.g., "Inventory is low in 15% of SKUs").
  2. **Insights**: 2-3 bullet points (e.g., "Overstocks in hunting category").
  3. **Recommendations**: 1-2 actions (e.g., "Reorder 500 units of top sellers").
- **Custom Responses**: In `core.py`, use Claude for non-SQL tasks (e.g., sentiment on returns). Prompt example: "Analyze return reasons: [list]".
- **Constraints**:
  - Limit to provided data; do not assume external knowledge.
  - Handle errors gracefully: If data is empty, return "No data available".
  - Use XML tags in prompts for structure (e.g., <insight>...</insight>).

## Best Practices
- **Prompt Engineering**: Be clear and direct; use chain-of-thought (e.g., "First, review data; then, identify trends"). Incorporate examples from project schema.
- **Error Handling**: In code, wrap calls with try/except (as in `summarizer.py`); log via `logging`.
- **Performance**: Keep prompts under 2000 tokens; focus on retail metrics (sales, units, margins).
- **Hierarchical CLAUDE.md**: For subdirs (e.g., `/chatbot/`), add nested files with module-specific guidance (e.g., SQL validation rules).
- **Do's and Don'ts**:
  - Do: Ground in schema (e.g., use `as400_data.vendor_name1`).
  - Don't: Generate unbounded SQL; suggest LIMIT if unlimited.
- **Testing Outputs**: Always verify summaries against BigQuery results; use REPL for quick Pandas checks (e.g., `df.describe()`).

## Examples
- **Summary Prompt Example** (from `summarizer.py`):
  ```
  You are a retail analytics expert. Analyze this data:
  Query: Top items by sales
  Data: [df.head(10).to_string()]
  Provide: 1. Key findings paragraph. 2. 2-3 insights. 3. 1-2 opportunities.
  ```
  Expected Output: Structured Markdown with bold headers.

- **Custom Analysis**:
  Prompt: "Using weighting_logic.py, suggest improvements for CoverageMetrics."
  Claude Response: Analyze code, propose additions like ML forecasting.

## UI/UX Design Insights
- **Navigation Sidebar Observations**:
  - Implemented a sidebar with key navigation buttons:
    * Chat Assistant: Provides interactive AI-driven interface
    * Analytics Dashboard: Displays key retail metrics and insights
    * Seasonality Configuration: Allows users to set seasonal parameters
  - Session cost tracking is currently hidden, suggesting potential future feature for user transparency
  - Use of emotive icons (💬, 📊, 🌱) to make navigation more intuitive and engaging

## References
- Anthropic Docs: [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- Project Integration: See `core.py` for AI calls.

This file ensures Claude operates efficiently within Super Gemini. Update as project evolves.