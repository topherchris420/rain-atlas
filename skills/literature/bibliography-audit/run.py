import re
import unicodedata

REQUIRED = {
    "article": [("author",), ("title",), ("journal",), ("year",)],
    "book": [("author", "editor"), ("title",), ("publisher",), ("year",)],
    "inproceedings": [("author",), ("title",), ("booktitle",), ("year",)],
}
DEFAULT_REQUIRED = [("author", "editor"), ("title",), ("year",)]
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
LIMITATION = "syntax checked offline; existence and content of the reference were not verified"


def _value(text, i):
    """Parse one field value starting at text[i]; return (value, next index)."""

    if text[i] == "{":
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return text[i + 1 : j], j + 1
            j += 1
        raise ValueError("unbalanced braces")
    if text[i] == '"':
        j = i + 1
        while j < len(text) and not (text[j] == '"' and text[j - 1] != "\\"):
            j += 1
        return text[i + 1 : j], j + 1
    match = re.match(r"[^,}\s]+", text[i:])
    return (match.group(0) if match else ""), i + (match.end() if match else 0)


def parse(text):
    entries = []
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        kind = match.group(1).lower()
        if kind in {"comment", "string", "preamble"}:
            continue
        i, fields, unparsed = match.end(), {}, []
        while i < len(text):
            while i < len(text) and text[i] in " \t\r\n,":
                i += 1
            if i >= len(text) or text[i] == "}":
                break
            name = re.match(r"([\w-]+)\s*=\s*", text[i:])
            if not name:
                unparsed.append(text[i : i + 30])
                break
            i += name.end()
            value, i = _value(text, i)
            if "#" in value and not value.strip().startswith("{"):
                unparsed.append(name.group(1))
            fields[name.group(1).lower()] = " ".join(value.split())
        entries.append({"type": kind, "key": match.group(2), "fields": fields, "unparsed": unparsed,
                        "offset": match.start()})
    return entries


def _norm_title(title):
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text.replace("{", "").replace("}", "")).strip()


def run(inputs, ctx):
    text = inputs["bibtex"]
    if isinstance(text, dict):
        text = ctx.read_bytes(text).decode("utf-8")
    current_year = int(inputs.get("current_year", 2100))
    entries = parse(text)
    problems = []
    seen_doi, seen_title = {}, {}
    for e in entries:
        f = e["fields"]
        for alternatives in REQUIRED.get(e["type"], DEFAULT_REQUIRED):
            if not any(f.get(a) for a in alternatives):
                problems.append({"key": e["key"], "kind": "missing-field", "detail": " or ".join(alternatives)})
        if "doi" in f:
            doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", f["doi"], flags=re.I)
            if not DOI.match(doi):
                problems.append({"key": e["key"], "kind": "malformed-doi", "detail": f["doi"]})
            elif doi.lower() in seen_doi:
                problems.append({"key": e["key"], "kind": "duplicate", "detail": f"same DOI as {seen_doi[doi.lower()]}"})
            else:
                seen_doi[doi.lower()] = e["key"]
        if "year" in f:
            if not re.fullmatch(r"\d{4}", f["year"]):
                problems.append({"key": e["key"], "kind": "malformed-year", "detail": f["year"]})
            elif int(f["year"]) > current_year:
                problems.append({"key": e["key"], "kind": "future-year", "detail": f["year"]})
        if f.get("title"):
            ident = (_norm_title(f["title"]), f.get("year"))
            if ident in seen_title and not any(p["key"] == e["key"] and p["kind"] == "duplicate" for p in problems):
                problems.append({"key": e["key"], "kind": "duplicate",
                                 "detail": f"same title and year as {seen_title[ident]}"})
            seen_title.setdefault(ident, e["key"])
        for name in e["unparsed"]:
            problems.append({"key": e["key"], "kind": "unparsed", "detail": name})
    by_type = {}
    for e in entries:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    kinds = {}
    for p in problems:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    ctx.log(f"audited {len(entries)} entr(ies); {len(problems)} problem(s)")
    return {
        "entries": [{"key": e["key"], "type": e["type"], "fields": sorted(e["fields"])} for e in entries],
        "problems": problems,
        "summary": {"entries": len(entries), "problems": len(problems), "by_type": by_type, "by_kind": kinds,
                    "limitation": LIMITATION},
    }
