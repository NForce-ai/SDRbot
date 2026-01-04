---
name: crm-migration
description: Migrate data between CRMs using the available CRM tools
---

# CRM Migration Skill

Use this skill when the user asks to migrate, copy, sync, or transfer data between CRMs.

Before you begin make sure we are operating in privileged mode, otherwise the user must enable it via `/setup` 

## Deliverable

**Successful migration** with records transferred from source to target CRM.

---

## Phase 1: Schema Discovery

Do a quick schema sync, then instantiate subagents for schema discovery. DO NOT call schema tools directly.

Schema tools return 10,000+ tokens. Call them directly and you'll overflow your context.

### Subagent for Source CRM

Spawn a general-purpose subagent:

```
Query the [SOURCE CRM] schema and return a CONCISE summary of all business objects and their respective fields.

Return markdown tables. Do NOT include raw API responses.
```

### Subagent for Target CRM

```
Query the [TARGET CRM] schema and return a CONCISE summary of all business objects and their respective fields.

Return markdown tables. Do NOT include raw API responses.
```

---

## Phase 2: Clarifications

Ask questions **one at a time** to avoid overwhelming the user.

Base questions (ask additional questions at your discretion based on context):

- **Object types**: Contacts? Companies? Deals? All?
- **Filters**: All records or a subset?
- **Record owner**: Which user should own the imported records?
- **Emails**: Migrate email history? (Default: NO)
- **Execution mode**: Sequential or concurrent? (see below)

**Note**: Duplicates are always skipped (records already in target CRM are not overwritten).

### Execution Mode

Present both options to the user:

**Sequential** (safer, slower)
- Processes one record at a time
- Easier to debug if issues occur
- Best for: small migrations (<100 records), first-time migrations, unstable APIs

**Concurrent** (faster, requires rate limit awareness)
- Processes multiple records in parallel
- Significantly faster for large datasets
- Must implement exponential backoff when hitting 429 (rate limit) responses
- Best for: large migrations (1000+ records), stable APIs, repeat migrations

If user chooses **concurrent**, confirm rate limit assumptions:
- "The target CRM ([name]) has a rate limit of ~X requests/second. I'll use a concurrency of Y. Does this sound right?"
- Mention if the CRM has known rate limit quirks (e.g., Pipedrive's strict 2 req/s)

### Pipeline Handling (if migrating deals/opportunities)

If the source CRM has **multiple pipelines**, propose options to the user:

**Option A: Map to Target Pipelines (1:1)**
- Best when target CRM supports multiple pipelines
- Create matching pipelines in target, map stages within each

**Option B: Merge into Single Pipeline**
- Combine all deals into one pipeline
- Create a custom field (e.g., `source_pipeline`) to preserve origin
- Map all stages to a unified set

**Option C: Create Pipeline Tracking Fields**
- Best when target CRM has limited/no pipeline support
- Create a custom field (e.g., `source_pipeline`) to preserve origin
- Create new fields (e.g. `reseller_pipeline_stage`) to track each pipeline stage separately.

Present these options with context about target CRM capabilities. Let the user decide based on their workflow needs.

---

## Phase 3: Write Migration Plan

Create `files/<source>_to_<target>_migration_plan.md`:

```markdown
# Migration Plan: [Source] to [Target]

## Summary

| Item | Value |
|------|-------|
| Source CRM | [Name] |
| Target CRM | [Name] |
| Entities | Companies, People, Opportunities |
| Estimated Records | ~X companies, ~Y people, ~Z deals |
| Record Owner | [User Name] (ID: xxx-xxx) |
| Execution Mode | Sequential / Concurrent (N req/s) |

## Migration Order

**IMPORTANT**: This section defines the stages for the migration executor. Each item becomes a separate script that is validated and executed independently.

List entities in dependency order (entities with no dependencies first):

1. Companies (no dependencies)
2. People (linked to companies)
3. Opportunities (linked to companies + people)

To skip an entity, simply omit it from this list.

## Field Mappings

### Companies

| Source Field | Target Field | Transform |
|--------------|--------------|-----------|
| name | name | Direct |
| domain | domainName | Direct |

### People

| Source Field | Target Field | Transform |
|--------------|--------------|-----------|
| name | firstName + lastName | Split |
| email | emails.primaryEmail | Direct |
| org_id | companyId | ID lookup |

### Opportunities

| Source Field | Target Field | Transform |
|--------------|--------------|-----------|
| title | name | Direct |
| value | amount | Direct |
| stage | stage | Map values |

## Pipeline Strategy

| Item | Value |
|------|-------|
| Source Pipelines | [List: Sales, Enterprise, etc.] |
| Target Pipelines | [List or "Single pipeline"] |
| Strategy | [Option A/B/C from clarifications] |

### Pipeline Mappings (if Option A)

| Source Pipeline | Target Pipeline |
|-----------------|-----------------|
| Sales | Sales |
| Enterprise | Enterprise Deals |

### Stage Mappings

For each pipeline (or unified if merging):

**[Pipeline Name]**

| Source Stage | Target Stage |
|--------------|--------------|
| Lead In | NEW_LEAD |
| Won | CLOSED_WON |

## Custom Fields to Create

| Object | Field Name | Type | Options |
|--------|------------|------|---------|
| person | leadSource | SELECT | ... |
| opportunity | source_pipeline | TEXT | (if Option B/C) |
| opportunity | source_pipeline_stage | TEXT | (if Option C) |
```

### ⛔ CHECKPOINT: Get User Approval

**STOP HERE.** Present the migration plan to the user and ask:

> "Here's the migration plan. Please review the field mappings and let me know if this looks correct, or if you'd like any changes before I proceed."

**Do NOT proceed to Phase 4 until the user explicitly approves the plan.**

---

## Phase 4: Create Custom Fields

If the migration plan identifies custom fields that need to be created in the target CRM:

1. **Create each field** using admin tools (e.g., `twenty_admin_create_field`)
2. **Get user approval** for each field before creating

Tools are automatically regenerated when schema changes are detected.

Example for Twenty CRM:
```
twenty_admin_create_field(
    object_name="person",
    name="leadSource",
    label="Lead Source",
    type="SELECT",
    options=[
        {"value": "WEBSITE", "label": "Website", "color": "blue", "position": 0},
        {"value": "REFERRAL", "label": "Referral", "color": "green", "position": 1}
    ]
)
```

---

## Phase 5: Execute Migration

IMPORTANT: Create the necessary custom fields yourself before engaging the subagent since the subagent needs them to already be in place.

**DELEGATE TO `migration-executor` SUBAGENT**

The executor uses a **staged approach**:
- Creates one script per entity in the Migration Order
- Validates and executes each stage independently
- Returns between stages for visibility (natural checkpoints)

### Spawning the Executor

```
Source CRM: [SOURCE]
Target CRM: [TARGET]
Migration plan: files/<source>_to_<target>_migration_plan.md

Execute the migration.
```

### Handling Executor Responses

The executor returns status-prefixed messages. Handle each stage:

| Response | Your Action |
|----------|-------------|
| `NEED_INPUT: <question>` | Ask the user, re-invoke executor with answer |
| `WRITING: <stage>` | Inform user which stage script is being written |
| `VALIDATING: <stage>` | Inform user validation is running for this stage |
| `READY_FOR_LIVE: <stage> - <summary>` | Show summary, get approval, re-invoke with "Approved" |
| `STAGE_COMPLETE: <stage> done. Proceeding to <next>.` | Inform user of progress (no action needed, executor continues) |
| `EXECUTING: <stage>` | Inform user stage is running |
| `DONE: <summary>` | Report final results (all stages complete) |
| `ERROR: <details>` | Report error, discuss options with user |

### Re-invoking the Executor

When re-invoking after user input:

```
[Previous status]: <executor's last response>
[User response]: <user's decision or answer>

Continue.
```

The executor maintains state across invocations and continues from where it left off.

### Troubleshooting & Repairs

If issues arise, **continue delegating to the migration-executor**. Do NOT attempt fixes yourself.

The executor is better equipped because it:
- Has full context of each stage script and field mappings
- Knows which records succeeded/failed and why
- Can fix a single stage without affecting others

When re-invoking for troubleshooting:

```
[Issue]: <description of the problem>
[Stage affected]: <which stage, if known>
[User request]: <what the user wants fixed>

Investigate and repair.
```

