---
name: crm-migration
description: Efficiently migrate data between CRMs using Python scripts with batching and pagination
---

# CRM Migration Skill

Use this skill when the user asks to migrate, copy, sync, or transfer data between CRMs.

## Code Execution

**DO NOT** use individual CRM tools for migrations. Write a Python script instead:
- Individual tools = 1 API request per record = slow and expensive
- Scripts can batch, paginate, and handle errors properly

## Migration Workflow

### Step 1: Understand the Requirements

Ask the user:
1. **Source CRM**: Where is the data coming from?
2. **Target CRM**: Where should data go?
3. **Object types**: Contacts? Companies? Deals? All?
4. **Filters**: All records or a subset?
5. **Duplicates**: Skip existing or update them?

### Step 2: Analyze BOTH CRM Schemas

**You MUST analyze both source and target CRM schemas before writing any code.**

Query schemas using admin tools:

```python
# Example: Pipedrive (source) -> Twenty (target)

# Source CRM
pipedrive_admin_list_person_fields()
pipedrive_admin_list_organization_fields()
pipedrive_admin_list_deal_fields()

# Target CRM
twenty_admin_list_objects()
twenty_admin_list_fields(object_id="...")
```

Present findings to the user:
- Fields available in source
- Fields available in target
- Gaps or mismatches that need addressing (may need to create custom fields)

### Step 3: Build Field Mapping

Create a mapping based on the schemas you discovered:

```python
FIELD_MAP = {
    # Source field -> Target field
    "name": "name",
    "email": "emails",  # May need transform if structure differs
    "phone": "phones",
    "abc123_lead_score": "leadScore",  # Custom field
}

def transform(source_record):
    """Transform source record to target format."""
    return {
        target: source_record.get(source)
        for source, target in FIELD_MAP.items()
        if source_record.get(source) is not None
    }
```

If mapping is ambiguous, **ask the user**.

### Step 4: Write the Migration Script

Create a Python script with dry-run support:

```python
#!/usr/bin/env python3
"""Migration: HubSpot Contacts -> Salesforce Leads"""

import json
from sdrbot_cli.auth.hubspot import get_client as get_hubspot_client
from sdrbot_cli.auth.salesforce import get_client as get_salesforce_client

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
    result["LastName"] = result.get("LastName") or "Unknown"
    result["Company"] = result.get("Company") or "Unknown"
    return result

def migrate(dry_run=True):
    hs = get_hubspot_client()
    sf = get_salesforce_client()

    all_records = []
    print("Fetching contacts from HubSpot...")

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

    print("\nMigrating to Salesforce...")
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
    migrate(dry_run=True)
```

### Step 5: Execute and Report

1. Run dry run first
2. Review sample output with user
3. If approved, set `dry_run=False` and run again
4. Report: records migrated, errors, error log location

## CRM Clients

```python
from sdrbot_cli.auth.hubspot import get_client as get_hubspot_client
from sdrbot_cli.auth.salesforce import get_client as get_salesforce_client
from sdrbot_cli.auth.pipedrive import get_pipedrive_client
from sdrbot_cli.auth.zohocrm import get_zoho_client
from sdrbot_cli.auth.attio import AttioClient
from sdrbot_cli.auth.twenty import TwentyClient
```

## CRM Quirks

| CRM | Pagination | Batch Limit | Notes |
|-----|------------|-------------|-------|
| HubSpot | `after` cursor | 100 | Must explicitly request properties |
| Salesforce | - | 10,000 (bulk) | Required: LastName (Contact), Company+LastName (Lead) |
| Pipedrive | `start` + `limit` | - | Custom fields are 40-char hashes; 100 req/10s rate limit |
| Attio | cursor | - | Records are versioned |
| Zoho | COQL | 100 | Module names are case-sensitive |
| Twenty | `startingAfter` cursor | - | No native batch API |

## Error Handling

1. Wrap batches in try/except — don't let one error stop everything
2. Log errors with source record context
3. Use upsert when available
4. Validate required fields before sending
5. Checkpoint progress for large migrations

## Deduplication Example

```python
def migrate_with_dedup(source_contacts, target_client):
    """Skip duplicates based on email."""
    existing_emails = set()
    for page in get_target_contacts(target_client):
        for contact in page:
            if email := contact.get("email"):
                existing_emails.add(email.lower())

    new_contacts = [
        c for c in source_contacts
        if c.get("email", "").lower() not in existing_emails
    ]

    print(f"Skipping {len(source_contacts) - len(new_contacts)} duplicates")
    return batch_create(target_client, new_contacts)
```
