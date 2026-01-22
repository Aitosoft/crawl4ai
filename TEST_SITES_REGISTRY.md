# Test Sites Registry

**Purpose:** Shared registry of Finnish SME websites for testing crawl4ai capabilities. Used by both `crawl4ai-aitosoft` and `aitosoft-platform` (MAS) repos.

**Last Updated:** 2026-01-21

---

## Test Site Categories

### Tier 1: Core Test Sites (Always Test)

These sites represent diverse patterns we MUST handle correctly:

| Site | Type | Key Characteristics | Contact Page | Decision Maker |
|------|------|---------------------|--------------|----------------|
| **talgraf.fi** | Software (20 employees) | Cookie consent, 20+ contacts, LinkedIn links | `/yhteystiedot` | Toni Kemppinen (CEO) |
| **tilitoimistovahtivuori.fi** | Accounting (small) | Obfuscated emails `(at)`, WordPress | `?page_id=77` | Jaana Toppinen, Kirsi Haltia |
| **accountor.com/fi** | Enterprise (large) | Heavy cookie wall, multi-country | `/finland/suuryritykselle` | Kari Putkonen, Jani Järvensivu |
| **monidor.fi** | IoT/Hardware | Clean site, minimal tracking | `/fi/fi-yritys/yritys/` | Mikko Savola (CEO) |

**Why these 4:**
- Talgraf: Cookie consent + structured contact data (cards)
- Vahtivuori: Email obfuscation + split-line formatting
- Accountor: Cookie wall edge case (requires `magic: true`)
- Monidor: Clean baseline (should always work fast)

### Tier 2: Extended Test Sites (Regression Testing)

Test these when making significant changes:

| Site | Type | Key Characteristics | Contact Page | Decision Maker |
|------|------|---------------------|--------------|----------------|
| **jpond.fi** | Software consulting | All emails obfuscated, long Google Maps URL | `/yhteystiedot/` | Janne Lampi |
| **neuroliitto.fi** | Non-profit | Cookiebot tracking, deep nested paths | `/yhteystiedot/hallinto-ja-tukipalvelut/` | Helena Ylikylä-Leiva |
| **solwers.com** | Public company | Names in ALL CAPS, investor relations section | `/sijoittajat/hallinnointi/#johtoryhma` | Johan Ehrnrooth (CEO) |
| **caverna.fi** | Restaurant | Multiple phone formats, minimal web presence | Homepage | No decision-maker |
| **showell.com** | SaaS (redirects .fi→.com) | Heavy tracking (39 Cookiebot URLs), no contacts on homepage | N/A | N/A |

### Tier 3: Edge Cases (Specific Feature Testing)

Test these when working on specific features:

| Site | Purpose | What It Tests |
|------|---------|---------------|
| **talgraf.fi** (homepage) | Timeout handling | Homepage times out, contact page works |
| **accountor.com/fi/finland** | Cookie wall bypass | Requires `magic: true` + `scan_full_page: true` |
| **solwers.com** press releases | Press contact extraction | Phone in +358 format, press contact info |
| **neuroliitto.fi** | Deep navigation | Contacts 3+ levels deep in site structure |

---

## Test Site Metadata

### talgraf.fi
```json
{
  "domain": "talgraf.fi",
  "company_name": "Talgraf Oy",
  "y_tunnus": "2690824-4",
  "type": "software_company",
  "size": "20_employees",
  "homepage": "https://www.talgraf.fi",
  "contact_page": "https://www.talgraf.fi/yhteystiedot",
  "expected_contacts": {
    "total": 20,
    "decision_makers": [
      {
        "name": "Toni Kemppinen",
        "title": "Toimitusjohtaja",
        "phone": "050 361 6485",
        "email": "toni.kemppinen@talgraf.fi",
        "linkedin": "https://www.linkedin.com/in/tonikemppinen/"
      },
      {
        "name": "Sanna Kemppinen",
        "title": "Henkilöstöjohtaja",
        "phone": "044 533 1704",
        "email": "sanna.kemppinen@talgraf.fi"
      },
      {
        "name": "Renne Pöysä",
        "title": "Myyntijohtaja",
        "phone": "050 336 6418",
        "linkedin": "https://www.linkedin.com/in/renne-poysa/"
      }
    ]
  },
  "challenges": [
    "cookie_consent",
    "homepage_timeout",
    "multiple_phone_formats"
  ],
  "test_priority": "tier_1",
  "notes": "Email pattern explicitly stated: 'etunimi.sukunimi@talgraf.fi'. 5 office locations."
}
```

### tilitoimistovahtivuori.fi
```json
{
  "domain": "tilitoimistovahtivuori.fi",
  "company_name": "Tilitoimisto Vahtivuori Oy / Jotava Oy",
  "y_tunnus": ["2588511-6", "2634545-3"],
  "type": "accounting_firm",
  "size": "small",
  "homepage": "https://tilitoimistovahtivuori.fi",
  "contact_page": "https://tilitoimistovahtivuori.fi/?page_id=77",
  "expected_contacts": {
    "total": 14,
    "decision_makers": [
      {
        "name": "Jaana Toppinen",
        "title": "Yrittäjä",
        "phone": "044 770 7707",
        "email": "jaana.toppinen@tilitoimistovahtivuori.fi"
      },
      {
        "name": "Kirsi Haltia",
        "title": "Yrittäjä, KLT, MBA",
        "phone": "040 028 2080",
        "email": "kirsi.haltia@tilitoimistovahtivuori.fi"
      }
    ]
  },
  "challenges": [
    "obfuscated_emails_at",
    "split_line_email_format",
    "wordpress_page_id_urls"
  ],
  "test_priority": "tier_1",
  "notes": "Emails use 'name(at)domain.fi' format. Some split across lines. 2 offices."
}
```

### accountor.com
```json
{
  "domain": "accountor.com",
  "company_name": "Accountor (Aspia Group)",
  "type": "enterprise_accounting",
  "size": "large",
  "homepage": "https://www.accountor.com/fi/finland",
  "contact_pages": [
    "https://www.accountor.com/fi/finland/suuryritykselle",
    "https://www.accountor.com/fi/finland/pk-ja-kasvuyritykselle"
  ],
  "expected_contacts": {
    "decision_makers": [
      {
        "name": "Jani Järvensivu",
        "title": "Myyntijohtaja",
        "phone": "+358 40 713 3683",
        "email": "jani.jarvensivu@aspia.fi",
        "page": "/suuryritykselle"
      },
      {
        "name": "Kari Putkonen",
        "title": "Myyntijohtaja, pk-yritykset",
        "phone": "+358447386009",
        "email": "kari.putkonen@aspia.fi",
        "page": "/pk-ja-kasvuyritykselle"
      }
    ]
  },
  "challenges": [
    "cookie_consent_wall",
    "requires_magic_true",
    "requires_scan_full_page",
    "multi_country_site"
  ],
  "test_priority": "tier_1",
  "notes": "CRITICAL TEST CASE: Requires `magic: true` + `scan_full_page: true` or returns only 32 tokens."
}
```

### monidor.fi
```json
{
  "domain": "monidor.fi",
  "company_name": "Monidor Oy",
  "type": "iot_hardware",
  "size": "small",
  "homepage": "https://monidor.fi",
  "redirects_to": "https://monidor.com",
  "contact_page": "https://monidor.com/fi/fi-yritys/yritys/",
  "expected_contacts": {
    "decision_makers": [
      {
        "name": "Mikko Savola",
        "title": "Toimitusjohtaja",
        "phone": "+358 50 378 8890",
        "email": "mikko.savola@monidor.com"
      }
    ]
  },
  "challenges": [
    "domain_redirect"
  ],
  "test_priority": "tier_1",
  "notes": "Clean baseline site. Minimal tracking. Should always work fast."
}
```

---

## Testing Patterns & Learnings

### Cookie Consent Handling

| Pattern | Sites Affected | Solution | Test Command |
|---------|----------------|----------|--------------|
| **Cookiebot wall** (blocks content) | accountor.com | `magic: true` + `scan_full_page: true` | See V10 tests |
| **Cookiebot tracking** (pixel only) | neuroliitto.fi, showell.com | `removeCommonDomains` cleaning | Check for cookiebot.com URLs |
| **Finnish popup** (text at end) | talgraf.fi | No truncation needed - let LLM see it | Check tokens don't bloat >5k |
| **No consent** | monidor.fi, caverna.fi | Works with defaults | Fast baseline |

### Email Obfuscation Patterns

| Pattern | Example | Sites | LLM Handles? |
|---------|---------|-------|--------------|
| `(at)` inline | `name(at)domain.fi` | jpond.fi (all 19 emails) | ✅ Yes |
| `(at)` split-line | `name(at)\ndomain.fi` | vahtivuori.fi | ✅ Yes |
| Pattern statement | "Emails: firstname.lastname@company.fi" | talgraf.fi | ✅ Yes |
| `mailto:` links | `<a href="mailto:...">` | Most sites | ✅ Yes |

**Conclusion:** LLM semantic understanding handles all obfuscation. No regex preprocessing needed.

### Phone Number Formats

| Format | Example | Sites | Regex Pattern |
|--------|---------|-------|---------------|
| Finnish mobile (spaced) | `050 361 6485` | Most | `0[45]\d\s?\d{3}\s?\d{3,4}` |
| Finnish mobile (no space) | `0503616485` | Some | Same |
| International | `+358 50 361 6485` | accountor.com, monidor.fi | `\+358\s?\d{1,2}\s?\d+` |
| Finnish landline | `08 563 7500`, `010 574 3806` | talgraf.fi, jpond.fi | `0[18]\d?\s?\d{3}\s?\d{4}` |

**Conclusion:** LLM extracts all formats naturally. Regex can extract structured data but doesn't handle context.

### URL Navigation Patterns

| Finnish Term | English | Example Sites | Priority |
|--------------|---------|---------------|----------|
| `/yhteystiedot` | Contact info | talgraf.fi, jpond.fi | HIGH |
| `/ota-yhteytta` | Get in touch | Many | HIGH |
| `/yritys` | Company | monidor.fi | MEDIUM |
| `/johtoryhma` | Management team | solwers.com | HIGH |
| `/hallinto` | Administration | neuroliitto.fi | MEDIUM |
| `/tiimi` | Team | Some | MEDIUM |
| `?page_id=77` | WordPress contact | vahtivuori.fi | MEDIUM |
| `/en/contact` | English version | Many | MEDIUM |

---

## Cost Benchmarks (2026-01-21)

Based on V9/V10 testing with Azure crawl4ai deployment:

| Site Category | Avg Raw Tokens | Avg Cleaned Tokens | Cost per Page ($1/M input) |
|---------------|----------------|--------------------|-----------------------------|
| Clean sites | 600-1,500 | 600-1,400 | $0.0006-0.0014 |
| Medium sites | 1,500-4,000 | 1,400-3,800 | $0.0014-0.0038 |
| Cookie dialog sites | 4,000-15,000 | 3,800-14,500 | $0.0038-0.0145 |
| Heavy tracking (Showell) | 12,000-21,000 | 11,000-20,000 | $0.011-0.020 |

**For 1000 pages with mixed distribution:**
- Expected: ~3M tokens = $3 input cost
- Worst-case (all heavy): ~15M tokens = $15 input cost

---

## Quick Test Commands

### Test Single Site (Manual)
```bash
# Test contact page extraction
python test-aitosoft/test_site.py talgraf.fi --page yhteystiedot

# Test with heavy config (Accountor-type)
python test-aitosoft/test_site.py accountor.com --config heavy

# Test homepage vs contact page comparison
python test-aitosoft/test_site.py monidor.fi --compare
```

### Test All Tier 1 Sites
```bash
# Regression test - run before deploying changes
python test-aitosoft/test_regression.py --tier 1

# Full test suite (all tiers)
python test-aitosoft/test_regression.py --all
```

### Generate Test Report
```bash
# Create versioned test report (like MAS Claude's V1-V10)
python test-aitosoft/test_regression.py --tier 1 --report v11

# Output: test-aitosoft/reports/v11-test-results.md
```

---

## Test Success Criteria

### Per-Site Validation

| Check | Pass Criteria | Tier 1 Sites |
|-------|---------------|--------------|
| **Crawl succeeds** | `success: true`, status 200 | All 4 |
| **Markdown length** | >500 chars (not blocked) | All 4 |
| **Decision maker found** | Name + title present | All 4 |
| **Contact data found** | At least phone OR email | All 4 |
| **No data loss** | All expected contacts present | All 4 |
| **Token efficiency** | <5k tokens for contact page | 3/4 (Accountor exception) |

### Regression Test Gates

| Gate | Requirement | Why |
|------|-------------|-----|
| **All Tier 1 pass** | 4/4 sites return expected contacts | Core functionality |
| **No new timeouts** | Same timeout rate as baseline | Performance |
| **Token budget** | Avg tokens ≤ baseline + 10% | Cost control |
| **Zero data loss** | All known contacts still extracted | Quality |

---

## Adding New Test Sites

When adding a test site, document:

1. **Basic info:** domain, company name, Y-tunnus, type, size
2. **Contact page URL** and expected decision-makers
3. **Challenges:** What makes this site difficult? (cookie wall, obfuscation, etc.)
4. **Expected data:** At least 1-2 decision-makers with full contact info
5. **Test priority:** Which tier?

**Template:**
```json
{
  "domain": "example.fi",
  "company_name": "Example Oy",
  "y_tunnus": "1234567-8",
  "type": "industry_type",
  "size": "small|medium|large",
  "homepage": "https://example.fi",
  "contact_page": "https://example.fi/yhteystiedot",
  "expected_contacts": {
    "decision_makers": [
      {
        "name": "First Last",
        "title": "Toimitusjohtaja",
        "phone": "050 123 4567",
        "email": "first.last@example.fi"
      }
    ]
  },
  "challenges": ["list", "of", "challenges"],
  "test_priority": "tier_1|tier_2|tier_3",
  "notes": "Any special notes"
}
```

---

## Change Log

| Date | Change | Reason |
|------|--------|--------|
| 2026-01-21 | Initial registry created | Consolidate MAS V1-V10 test findings |
| 2026-01-21 | Added V10 cookie consent learnings | Document `magic: true` requirement |

---

## See Also

- [TESTING.md](TESTING.md) - Testing framework and best practices
- [test-aitosoft/](test-aitosoft/) - Test scripts and reports
- MAS repo exploration findings (link when available)
