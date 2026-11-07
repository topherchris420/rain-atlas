# ruff: noqa: F821
# BLACK GLASS: deterministic read-only Ghidra call graph exporter.
#@category BLACK_GLASS
#
# In Ghidra's analyzeHeadless:
#   -postScript BlackglassCalls.py usr/sbin/httpd /absolute/path/to/httpd /output/httpd.json
#
# The script never changes program bytes, names or types. It refuses to export
# when Ghidra's recorded import hash does not match the source ELF on disk.

import hashlib
import json
import os

MAX_FUNCTIONS = 2048
MAX_CALLS = 8192

args = getScriptArgs()
if len(args) != 3:
    raise ValueError("expected: <relative-binary-path> <absolute-ELF-path> <output-json-path>")
relative_path, binary_path, output_path = args
if not os.path.isfile(binary_path):
    raise ValueError("binary is missing: " + binary_path)

digest = hashlib.sha256()
with open(binary_path, "rb") as source:
    while True:
        block = source.read(1024 * 1024)
        if not block:
            break
        digest.update(block)
file_sha = digest.hexdigest().lower()
import_sha = currentProgram.getExecutableSHA256()
if import_sha is None or str(import_sha).lower() != file_sha:
    raise ValueError("Ghidra program import SHA256 does not match the source ELF")

manager = currentProgram.getFunctionManager()
listing = currentProgram.getListing()
found = []
for function in manager.getFunctions(True):
    found.append(function)
if len(found) > MAX_FUNCTIONS:
    raise ValueError("export exceeds 2048 functions; choose a smaller executable")
found.sort(key=lambda f: f.getEntryPoint().getOffset())

rows = []
total_calls = 0
for function in found:
    monitor.checkCancelled()
    calls = set()
    for instruction in listing.getInstructions(function.getBody(), True):
        for reference in instruction.getReferencesFrom():
            if not reference.getReferenceType().isCall():
                continue
            target = reference.getToAddress()
            callee = manager.getFunctionAt(target)
            if callee is None:
                callee = manager.getFunctionContaining(target)
            address = callee.getEntryPoint() if callee is not None else target
            calls.add("0x%x" % address.getOffset())
    total_calls += len(calls)
    if total_calls > MAX_CALLS:
        raise ValueError("export exceeds 8192 call edges; choose a smaller executable")
    rows.append({
        "entry": "0x%x" % function.getEntryPoint().getOffset(),
        "name": str(function.getName()),
        "size": int(function.getBody().getNumAddresses()),
        "calls": sorted(calls, key=lambda x: int(x, 16)),
    })

document = {
    "schema": "blackglass.native-calls/v1",
    "tool": "ghidra",
    "binary": relative_path,
    "sha256": "sha256:" + file_sha,
    "functions": rows,
}
if os.path.exists(output_path):
    raise ValueError("refusing to overwrite an existing native snapshot")
with open(output_path, "w") as output:
    output.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
print("BLACK GLASS: %d functions, %d calls, sha256:%s" %
      (len(rows), total_calls, file_sha))
