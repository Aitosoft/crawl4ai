# Temporary Accountor Contact Test

**Purpose**: Quick test to verify the Azure-deployed crawl4ai service can retrieve contact information from Accountor.com pages.

**Created**: 2026-01-21
**Status**: Temporary - delete when done

## What This Tests

Tests 4 pages from accountor.com to verify:
- ✅ Crawler can access the pages
- ✅ Markdown output contains contact names
- ✅ Markdown output contains contact emails/phones
- ✅ Markdown output contains job titles

## Run the Test

```bash
# Install dependencies
pip install -r temp-accountor-test/requirements.txt

# Run test
python temp-accountor-test/test_accountor_contacts.py
```

## Cleanup

When done testing:
```bash
rm -rf temp-accountor-test/
```

## Test Pages

1. https://www.accountor.com/fi/finland/suuryritykselle - Jani Järvensivu
2. https://www.accountor.com/fi/finland/pk-ja-kasvuyritykselle - Kari Putkonen
3. https://www.accountor.com/fi/finland/uusi/laura-yla-sulkava-... - Laura Ylä-Sulkava + others
4. https://www.accountor.com/fi/finland/ura/kirjanpitajasta-... - Joonas Taskinen
