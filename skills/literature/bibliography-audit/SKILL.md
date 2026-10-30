---
name: bibliography-audit
description: Audit a BibTeX bibliography offline for missing required fields, malformed DOIs and years, and likely duplicate entries. Use before citing references in a report so that problems are found rather than papered over; it never invents or completes metadata.
license: MIT
compatibility: Requires Python 3.11+ and the rain-atlas package (ATLAS executor). Works offline.
metadata:
  version: "1.0.0"
  domain: literature
---
# Bibliography audit

Parses BibTeX (`@type{key, field = {value} | "value" | number, ...}`) and
reports, per entry:

- missing required fields for its type (article: author, title, journal,
  year; book: author or editor, title, publisher, year; inproceedings:
  author, title, booktitle, year; others: author or editor, title, year);
- DOIs that do not match the `10.<registrant>/<suffix>` syntax;
- years that are not four digits or are in the future;
- likely duplicates: same DOI, or the same normalised title and year.

It also returns summary counts and per-type totals. Nothing is looked up or
filled in: a syntactically valid DOI may still not exist, and that is stated
as a limitation in every result.

## Limitations

- Offline syntax checks only; does not verify that a DOI resolves or that a
  reference says what it is cited for.
- Supports common BibTeX; `@string` macros and `#` concatenation are not
  expanded (entries using them are reported as unparsed fields).
