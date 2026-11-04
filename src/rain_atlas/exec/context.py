"""The object a skill's ``run(inputs, ctx)`` receives, plus result writing."""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
from typing import Any

from ..canonical import from_jsonable, to_jsonable

RESULT_FILE = "_result.json"


def valid_artifact_name(name: object) -> bool:
    """Portable single file name; reject traversal, devices and Windows streams."""
    return (isinstance(name, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", name))
            and not name.endswith((".", " "))
            and name.split(".")[0].upper() not in
            {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))})


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class SkillContext:
    """Paths, seed, artifacts and log for one invocation.

    Artifacts are files in the output directory. A reference to one is the
    JSON object ``{"$artifact": "<file name>", "sha256": "sha256:<hex>"}``;
    inputs use the same form for files the host copied into the input
    directory, and :meth:`load_array` verifies the hash before returning data.
    """

    def __init__(self, *, seed: int, skill_dir: str, input_dir: str, output_dir: str, tmp_dir: str):
        self.seed = int(seed)
        self.skill_dir = skill_dir
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.tmp_dir = tmp_dir
        self.messages: list[str] = []
        random.seed(self.seed)

    # randomness ---------------------------------------------------------
    def rng(self, *stream: int):
        """A numpy Generator derived from the run seed (and optional stream ids)."""

        import numpy as np  # noqa: PLC0415

        return np.random.default_rng(np.random.SeedSequence([self.seed, *stream]))

    # logging ------------------------------------------------------------
    def log(self, message: str) -> None:
        self.messages.append(str(message))

    # artifacts ----------------------------------------------------------
    def _input_path(self, ref: dict) -> str:
        name = ref["$artifact"]
        if not valid_artifact_name(name):
            raise ValueError(f"artifact names may not contain directories: {name!r}")
        return os.path.join(self.input_dir, name)

    def read_bytes(self, ref: dict) -> bytes:
        with open(self._input_path(ref), "rb") as fh:
            data = fh.read()
        if "sha256" in ref and _sha256(data) != ref["sha256"]:
            raise ValueError(f"artifact {ref['$artifact']!r} does not match its recorded hash")
        return data

    def load_array(self, ref: dict):
        import numpy as np  # noqa: PLC0415

        return np.load(io.BytesIO(self.read_bytes(ref)), allow_pickle=False)

    def write_bytes(self, name: str, data: bytes) -> dict:
        if not valid_artifact_name(name) or name == RESULT_FILE:
            raise ValueError(f"invalid artifact name {name!r}")
        with open(os.path.join(self.output_dir, name), "wb") as fh:
            fh.write(data)
        return {"$artifact": name, "sha256": _sha256(data)}

    def save_array(self, name: str, array) -> dict:
        import numpy as np  # noqa: PLC0415

        buffer = io.BytesIO()
        np.save(buffer, np.asarray(array), allow_pickle=False)
        return self.write_bytes(name, buffer.getvalue())

    def save_text(self, name: str, text: str) -> dict:
        return self.write_bytes(name, text.encode("utf-8"))


def finish(ctx: SkillContext, *, status: str, outputs: Any = None, error: dict | None = None,
           extra: dict | None = None) -> int:
    payload = {"status": status, "log": ctx.messages}
    if outputs is not None:
        payload["outputs"] = to_jsonable(outputs)
    if error is not None:
        payload["error"] = error
    if extra:
        payload.update(extra)
    with open(os.path.join(ctx.output_dir, RESULT_FILE), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, allow_nan=False)
    return 0 if status == "ok" else 1


def decode_outputs(payload: dict) -> Any:
    return from_jsonable(payload.get("outputs"))
