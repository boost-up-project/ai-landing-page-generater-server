from __future__ import annotations

import html as html_module
import re
from pathlib import Path

from app.landing.schemas import EditableImage, EditableTarget

COPY_PATTERN = re.compile(
    r"(<(?P<tag>[a-z][\w:-]*)\b(?=[^>]*\bdata-editable\s*=\s*['\"]copy['\"])[^>]*>)"
    r"(?P<content>.*?)"
    r"(</(?P=tag)\s*>)",
    re.IGNORECASE | re.DOTALL,
)
IMAGE_PATTERN = re.compile(
    r"<img\b(?=[^>]*\bdata-editable\s*=\s*['\"]image['\"])[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
ATTRIBUTE_PATTERN = re.compile(
    r"(?P<name>[\w:-]+)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
ROOT_PATTERN = re.compile(
    r"<[a-z][\w:-]*\b(?P<attributes>[^>]*)>", re.IGNORECASE | re.DOTALL
)
LAYOUT_VARIANT_ATTRIBUTE_PATTERN = re.compile(
    r"\s+data-layout-variant\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL
)


def inspect_editable_targets(source: str) -> list[EditableTarget]:
    targets = [
        EditableTarget(
            kind="copy",
            current_value=html_module.unescape(
                _strip_tags(match.group("content"))
            ).strip(),
        )
        for match in COPY_PATTERN.finditer(source)
    ]
    targets.extend(
        EditableTarget(kind="image", current_value=_attribute(match.group(0), "src"))
        for match in IMAGE_PATTERN.finditer(source)
    )
    return targets


def component_metadata(source: str, filename: str) -> tuple[str, str]:
    root = ROOT_PATTERN.search(source)
    attributes = root.group("attributes") if root else ""
    fallback = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    name = _attribute(attributes, "data-component-name") or fallback or "Component"
    category = _attribute(attributes, "data-component-category") or "기본"
    return name, category


def component_layout_options(source: str) -> list[str]:
    root = ROOT_PATTERN.search(source)
    attributes = root.group("attributes") if root else ""
    options = _attribute(attributes, "data-layout-options").split()
    return options or ["source"]


def apply_layout_variant(source: str, layout_variant: str) -> str:
    """Store an allowed layout selection without changing the source DOM structure."""
    root = ROOT_PATTERN.search(source)
    if root is None:
        return source
    tag = root.group(0)
    updated = _set_attribute(tag, "data-layout-variant", layout_variant)
    return f"{source[: root.start()]}{updated}{source[root.end() :]}"


def apply_editable_values(
    source: str,
    copy_values: list[str],
    image_values: list[EditableImage],
) -> str:
    copy_index = 0

    def replace_copy(match: re.Match[str]) -> str:
        nonlocal copy_index
        value = html_module.escape(copy_values[copy_index], quote=False)
        copy_index += 1
        return f"{match.group(1)}{value}{match.group(4)}"

    result = COPY_PATTERN.sub(replace_copy, source)
    image_index = 0

    def replace_image(match: re.Match[str]) -> str:
        nonlocal image_index
        value = image_values[image_index]
        image_index += 1
        tag = match.group(0)
        if value.asset_filename:
            tag = _set_attribute(tag, "src", f"asset://{value.asset_filename}")
        return _set_attribute(tag, "alt", value.alt)

    return IMAGE_PATTERN.sub(replace_image, result)


def editable_counts(source: str) -> tuple[int, int]:
    return len(COPY_PATTERN.findall(source)), len(IMAGE_PATTERN.findall(source))


def editable_structure(source: str) -> str:
    def normalize_copy(match: re.Match[str]) -> str:
        return f"{match.group(1)}__EDITABLE_COPY__{match.group(4)}"

    normalized = COPY_PATTERN.sub(normalize_copy, source)

    def normalize_image(match: re.Match[str]) -> str:
        tag = _set_attribute(match.group(0), "src", "__EDITABLE_IMAGE__")
        return _set_attribute(tag, "alt", "__EDITABLE_ALT__")

    return LAYOUT_VARIANT_ATTRIBUTE_PATTERN.sub(
        "", IMAGE_PATTERN.sub(normalize_image, normalized)
    )


def editable_image_sources(source: str) -> list[str]:
    return [
        _attribute(match.group(0), "src") for match in IMAGE_PATTERN.finditer(source)
    ]


def _set_attribute(tag: str, name: str, value: str) -> str:
    escaped = html_module.escape(value, quote=True)
    pattern = re.compile(
        rf"\b{re.escape(name)}\s*=\s*(['\"]).*?\1", re.IGNORECASE | re.DOTALL
    )
    if pattern.search(tag):
        return pattern.sub(f'{name}="{escaped}"', tag, count=1)
    closing = "/>" if tag.rstrip().endswith("/>") else ">"
    return f'{tag.rstrip()[: -len(closing)].rstrip()} {name}="{escaped}"{closing}'


def _attribute(source: str, name: str) -> str:
    for match in ATTRIBUTE_PATTERN.finditer(source):
        if match.group("name").casefold() == name.casefold():
            return html_module.unescape(match.group("value"))
    return ""


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)
