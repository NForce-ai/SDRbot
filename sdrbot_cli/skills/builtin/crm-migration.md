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

Ask the user:
1. **Object types**: Contacts? Companies? Deals? All?
2. **Filters**: All records or a subset?
3. **Duplicates**: Skip existing or update them?
4. **Record owner**: Which user should own the imported records?
5. **Emails**: Migrate email history? (Default: NO)

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

## Migration Order

1. Companies (no dependencies)
2. People (linked to companies)
3. Opportunities (linked to companies + people)

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

## Stage Mappings

| Source Stage | Target Stage |
|--------------|--------------|
| Lead In | NEW_LEAD |
| Won | CLOSED_WON |

## Custom Fields to Create

| Object | Field Name | Type | Options |
|--------|------------|------|---------|
| person | leadSource | SELECT | ... |
```

**Get user approval before proceeding.**

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

The `migration-executor` subagent owns the entire execution:
- Writing the migration script
- Running dry runs
- Fixing errors
- Executing live migration

### Spawning the Executor

```
Source CRM: [SOURCE]
Target CRM: [TARGET]
Migration plan: files/<source>_to_<target>_migration_plan.md

Execute the migration. Start by writing the script and running a dry run.
```

### Handling Executor Responses

The executor returns status-prefixed messages:

| Response | Your Action |
|----------|-------------|
| `NEED_INPUT: <question>` | Ask the user, re-invoke executor with answer |
| `READY_FOR_LIVE: <summary>` | Show summary to user, get approval, re-invoke with "Approved, proceed with --live" |
| `EXECUTING: <status>` | Inform user migration is running |
| `DONE: <summary>` | Report final results to user |
| `ERROR: <details>` | Report error, discuss options with user |

### Re-invoking the Executor

When re-invoking after user input, provide the context:

```
[Previous status]: <executor's last response>
[User response]: <user's decision or answer>

Continue the migration.
```

The executor maintains state across invocations and will continue from where it left off.

### Troubleshooting & Repairs

If issues arise during or after migration (failed records, data inconsistencies, mapping errors, etc.), **continue delegating to the migration-executor**. Do NOT attempt to fix issues yourself.

The executor is better equipped to handle repairs because it:
- Has full context of the migration script and field mappings
- Knows which records succeeded/failed and why
- Can make targeted fixes without re-running the entire migration
- Maintains the migration log for tracking what was attempted

When re-invoking for troubleshooting:

```
[Issue]: <description of the problem>
[User request]: <what the user wants fixed>

Investigate and repair.
```

---

## Notes

- The executor runs dry run by default - no data is modified until user approves the live migration
- Live migrations run in background to avoid timeout
- Progress can be monitored via `tail -f files/migration.log`
- If migration needs to restart: `python files/migration.py --reset --confirm`
