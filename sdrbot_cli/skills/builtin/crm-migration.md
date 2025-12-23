---
name: crm-migration
description: Efficiently migrate data between CRMs using Python scripts with batching and pagination
---

# CRM Migration Skill

Use this skill when the user asks to migrate, copy, sync, or transfer data between CRMs (e.g., "migrate contacts from HubSpot to Salesforce").

**NOTE**: If you need to create custom fields or objects in the target CRM before migrating,
enable **Privileged Mode** via `/setup` > Privileged Mode. This loads admin tools for schema management.

## Why Use Code Execution for Migrations

**DO NOT** use individual CRM tools (like `hubspot_search_contacts`, `salesforce_create_contact`) for migrations. This is inefficient because:
- Each tool call = 1 API request = high latency
- Token usage explodes with large datasets
- No batching or error handling

**INSTEAD**, write and execute a Python migration script that:
- Uses the CRM clients directly (they support batching)
- Handles pagination internally
- Provides progress reporting
- Handles errors gracefully

## Migration Workflow

### Step 1: Understand the Requirements

Ask the user:
1. **Source CRM**: Where is the data coming from?
2. **Target CRM**: Where should data go?
3. **Object types**: Contacts? Companies? Deals? All?
4. **Filters**: All records or a subset (e.g., "contacts created this year")?
5. **Duplicates**: Skip existing records or update them?

### Step 2: Analyze BOTH CRMs (CRITICAL)

**YOU MUST analyze BOTH the source AND target CRM schemas before writing any migration code.**

This step is MANDATORY - do not skip it. You need to understand:
1. **Source CRM schema**: What fields exist? What are their types? What data is available?
2. **Target CRM schema**: What fields exist? What are required vs optional? What are the field types?
3. **Gaps and mismatches**: Fields in source that don't exist in target (may need to create custom fields)

**Option A: Use Admin Tools (Recommended)**

If Privileged Mode is enabled, query schemas for BOTH source AND target:

```python
# Example: Pipedrive (source) -> Twenty (target)

# 1. Analyze SOURCE CRM (Pipedrive)
pipedrive_admin_list_person_fields()      # Contact fields
pipedrive_admin_list_organization_fields() # Company fields
pipedrive_admin_list_deal_fields()        # Deal fields

# 2. Analyze TARGET CRM (Twenty)
twenty_admin_list_objects()               # All object types
twenty_admin_list_fields(object_id="...")  # Fields for each object
```

**Option B: Read Generated Tools (Fallback)**

If not in Privileged Mode, examine the generated tools for BOTH CRMs:

```python
# 1. Analyze SOURCE CRM
read_file("generated/{source_crm}_tools.py")

# 2. Analyze TARGET CRM
read_file("generated/{target_crm}_tools.py")

# Look at create_* function parameters to understand field schemas
```

**After analyzing both CRMs**, present your findings to the user:
- List the fields you found in the source CRM
- List the fields you found in the target CRM
- Identify any gaps or mismatches that need to be addressed

### Step 3: Build Field Mapping

Compare source and target schemas, then create a mapping:

```python
# Example: Pipedrive -> Twenty mapping (discovered from schemas)
FIELD_MAP = {
    # Source field -> Target field
    "name": "name",
    "email": "emails",  # Different structure - may need transform
    "phone": "phones",
    # Custom fields discovered from schema
    "abc123_lead_score": "leadScore",
}

def transform(source_record):
    """Transform source record to target format."""
    return {
        target: source_record.get(source)
        for source, target in FIELD_MAP.items()
        if source_record.get(source) is not None
    }
```

If mapping is ambiguous, **ask the user**:
- "Source has `lead_status`, target has both `status` and `stage`. Which should I use?"
- "Should I create a custom field in the target for `revenue_band`?"

### Step 4: Write the Migration Script

Create a Python script with dry-run support:

```python
#!/usr/bin/env python3
"""Migration: HubSpot Contacts -> Salesforce Leads"""

import json
from datetime import datetime

from sdrbot_cli.auth.hubspot import get_client as get_hubspot_client
from sdrbot_cli.auth.salesforce import get_client as get_salesforce_client

# Field mapping (discovered in Step 3)
FIELD_MAP = {
    "email": "Email",
    "firstname": "FirstName",
    "lastname": "LastName",
    "phone": "Phone",
    "company": "Company",
}

def get_hubspot_contacts(client, batch_size=100):
    """Generator that yields HubSpot contacts in batches."""
    after = None
    while True:
        response = client.crm.contacts.basic_api.get_page(
            limit=batch_size,
            after=after,
            properties=list(FIELD_MAP.keys())
        )
        yield response.results

        if not response.paging or not response.paging.next:
            break
        after = response.paging.next.after

def transform_contact(hs_contact):
    """Map HubSpot contact to Salesforce Lead."""
    props = hs_contact.properties
    result = {}
    for source, target in FIELD_MAP.items():
        if props.get(source):
            result[target] = props[source]
    # Handle required fields
    result["LastName"] = result.get("LastName") or "Unknown"
    result["Company"] = result.get("Company") or "Unknown"
    return result

def migrate(dry_run=True):
    hs = get_hubspot_client()
    sf = get_salesforce_client()

    all_records = []
    print(f"Fetching contacts from HubSpot...")

    for batch in get_hubspot_contacts(hs):
        transformed = [transform_contact(c) for c in batch]
        all_records.extend(transformed)
        print(f"  Fetched {len(all_records)} records...")

    print(f"\nTotal records to migrate: {len(all_records)}")

    if dry_run:
        print("\n=== DRY RUN ===")
        print("Sample record:")
        print(json.dumps(all_records[0] if all_records else {}, indent=2))
        print("\nRun with dry_run=False to execute migration.")
        return

    # Execute migration
    print(f"\nMigrating to Salesforce...")
    results = sf.bulk.Lead.insert(all_records)

    success = sum(1 for r in results if r.get("success"))
    errors = [r for r in results if not r.get("success")]

    print(f"\nMigration complete!")
    print(f"  Success: {success}")
    print(f"  Errors: {len(errors)}")

    if errors:
        with open("files/migration_errors.json", "w") as f:
            json.dump(errors, f, indent=2)
        print(f"  Error details: files/migration_errors.json")

if __name__ == "__main__":
    migrate(dry_run=True)  # Change to False after reviewing dry run
```

### Step 5: Execute and Report

1. **Run dry run first**: `python files/migration_script.py`
2. Review the sample output with the user
3. If approved, edit script to set `dry_run=False` and run again
4. Report results: records migrated, errors encountered, error log location

## Available CRM Clients

```python
# HubSpot
from sdrbot_cli.auth.hubspot import get_client as get_hubspot_client
hs = get_hubspot_client()

# Salesforce
from sdrbot_cli.auth.salesforce import get_client as get_salesforce_client
sf = get_salesforce_client()

# Pipedrive
from sdrbot_cli.auth.pipedrive import get_pipedrive_client
pd = get_pipedrive_client()

# Zoho CRM
from sdrbot_cli.auth.zohocrm import get_zoho_client
zoho = get_zoho_client()

# Attio
from sdrbot_cli.auth.attio import AttioClient
attio = AttioClient()

# Twenty
from sdrbot_cli.auth.twenty import TwentyClient
twenty = TwentyClient()
```

## CRM-Specific Tips

### HubSpot
- Pagination: `basic_api.get_page()` with `after` cursor
- Batch create: `batch_api.create()` (up to 100 records)
- Must explicitly request properties in API calls

### Salesforce
- Batch operations: `sf.bulk.{Object}.insert()` (up to 10,000)
- Upsert with external ID: `sf.bulk.{Object}.upsert(external_id_field, records)`
- Required fields: LastName (Contact), Company+LastName (Lead)

### Pipedrive
- Pagination: `start` and `limit` parameters
- Custom fields: 40-character hash keys (use admin tools to discover)
- Rate limit: 100 requests per 10 seconds
- Schema discovery: `pipedrive_admin_list_*_fields()` tools

### Attio
- Cursor-based pagination
- Records are versioned - specify attributes to update
- Relations are separate from record data

### Zoho CRM
- Use COQL for complex queries
- Batch: `insertRecords` (100 max per call)
- Module names are case-sensitive

### Twenty
- REST API: `client.get()`, `client.post()`, etc.
- Endpoints: `/people`, `/companies`, `/opportunities`
- Pagination: `limit` and `startingAfter` parameters
- No native batch API - loop with individual requests
- Schema discovery: `twenty_admin_list_objects()`, `twenty_admin_list_fields()`

```python
# Twenty pagination example
def get_all_people(client, batch_size=100):
    """Generator that yields Twenty people in batches."""
    starting_after = None
    while True:
        params = {"limit": batch_size}
        if starting_after:
            params["startingAfter"] = starting_after

        response = client.get("/people", params=params)
        data = response.get("data", {})
        people = data.get("people", [])

        if not people:
            break

        yield people

        page_info = data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        starting_after = page_info.get("endCursor")
```

## Error Handling Best Practices

1. **Wrap batches in try/except** - Don't let one error stop the whole migration
2. **Log errors with context** - Include the source record for debugging
3. **Use upsert when possible** - Handles duplicates gracefully
4. **Validate required fields** - Check before sending to target CRM
5. **Checkpoint progress** - For large migrations, save state periodically

## Deduplication Example

```python
def migrate_with_dedup(source_contacts, target_client):
    """Migrate contacts, skipping duplicates based on email."""

    # Get existing emails from target
    existing_emails = set()
    for page in get_target_contacts(target_client):
        for contact in page:
            if email := contact.get("email"):
                existing_emails.add(email.lower())

    # Filter duplicates
    new_contacts = [
        c for c in source_contacts
        if c.get("email", "").lower() not in existing_emails
    ]

    print(f"Skipping {len(source_contacts) - len(new_contacts)} duplicates")
    return batch_create(target_client, new_contacts)
```
