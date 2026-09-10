"""Parse and validate Illustrator/Blender semantic sewing names."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_SEAM_NAME = re.compile(
    r"^(?:SEAM_)?(?P<seam_id>S\d{3,})_"
    r"(?P<panel>[A-Z][A-Z0-9]*)(?:_(?P<endpoint>[AB]))?$"
)


@dataclass(frozen=True, slots=True)
class SeamName:
    raw: str
    seam_id: str
    panel: str
    endpoint: str | None = None

    @property
    def path_name(self) -> str:
        prefix = "SEAM_" if self.raw.startswith("SEAM_") else ""
        return f"{prefix}{self.seam_id}_{self.panel}"


def parse_seam_name(name: str) -> SeamName | None:
    """Return semantic parts or ``None`` for unrelated/legacy names."""

    match = _SEAM_NAME.fullmatch(name.strip())
    if match is None:
        return None
    return SeamName(raw=name, **match.groupdict())


def pair_seam_paths(names: Iterable[str]) -> list[tuple[str, str]]:
    """Pair path groups by Sewing ID, rejecting ambiguous definitions."""

    by_id: dict[str, list[SeamName]] = {}
    for name in names:
        parsed = parse_seam_name(name)
        if parsed is None or parsed.endpoint is not None:
            continue
        by_id.setdefault(parsed.seam_id, []).append(parsed)

    pairs: list[tuple[str, str]] = []
    for seam_id in sorted(by_id):
        definitions = by_id[seam_id]
        panels = {item.panel for item in definitions}
        if len(definitions) != 2 or len(panels) != 2:
            detail = ", ".join(item.raw for item in definitions)
            raise ValueError(
                f"{seam_id} must define exactly two different panel paths; got: {detail}"
            )
        pairs.append((definitions[0].raw, definitions[1].raw))
    return pairs


def endpoint_marker_names(path_name: str) -> tuple[str, str]:
    parsed = parse_seam_name(path_name)
    if parsed is None or parsed.endpoint is not None:
        raise ValueError(f"Not a semantic seam path name: {path_name}")
    return f"{parsed.path_name}_A", f"{parsed.path_name}_B"


def validate_direction_markers(names: Iterable[str]) -> list[str]:
    """Return human-readable errors for incomplete A/B marker definitions."""

    available = set(names)
    errors: list[str] = []
    for path_a, path_b in pair_seam_paths(available):
        for path_name in (path_a, path_b):
            marker_a, marker_b = endpoint_marker_names(path_name)
            missing = [name for name in (marker_a, marker_b) if name not in available]
            if missing:
                errors.append(f"{path_name} missing direction markers: {', '.join(missing)}")
    return errors
