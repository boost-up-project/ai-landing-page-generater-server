from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

_BODY_PATTERN = re.compile(
    r"<body\b[^>]*>(?P<content>.*?)</body\s*>", re.IGNORECASE | re.DOTALL
)
_STYLE_PATTERN = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_PATTERN = re.compile(
    r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL
)
_EMBED_PATTERN = re.compile(
    r"<(?:iframe|object|embed)\b[^>]*>.*?</(?:iframe|object|embed)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_VOID_EMBED_PATTERN = re.compile(
    r"<(?:iframe|object|embed)\b[^>]*?/?>", re.IGNORECASE | re.DOTALL
)
_EVENT_ATTRIBUTE_PATTERN = re.compile(
    r"\s+on[\w:-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE | re.DOTALL
)
_JAVASCRIPT_URL_PATTERN = re.compile(
    r"\s+(?:href|src)\s*=\s*(['\"])\s*javascript:[^'\"]*\1", re.IGNORECASE | re.DOTALL
)
_TAG_PATTERN = re.compile(r"</?([a-z][\w:-]*)\b[^>]*?>", re.IGNORECASE | re.DOTALL)
_ROOT_TAG_PATTERN = re.compile(
    r"<([a-z][\w:-]*)\b(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL
)
_ASSET_URL_PATTERN = re.compile(
    r"(?P<attribute>\b(?:src|poster)\s*=\s*)(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)

_SECTION_TAGS = {"header", "section", "article", "footer"}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_LAYOUT_RUNTIME_STYLES = """
<style data-component-layout-runtime>
[data-layout-variant="media-left"],[data-layout-variant="media-right"]{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:clamp(16px,3vw,48px);align-items:center}
[data-layout-variant="media-left"]>:is(img,picture,video,figure){grid-column:1;grid-row:1}
[data-layout-variant="media-right"]>:is(img,picture,video,figure){grid-column:2;grid-row:1}
[data-layout-variant="media-top"]>:is(img,picture,video,figure){display:block;width:100%;margin:0 0 24px}
[data-layout-variant="centered"]{text-align:center}
[data-layout-variant="inline"]{display:flex;align-items:center;justify-content:space-between;gap:16px}
[data-layout-variant="cards"]{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}
[data-layout-variant="compact"]{padding-top:24px!important;padding-bottom:24px!important}
[data-layout-variant="spacious"]{padding-top:clamp(48px,8vw,120px)!important;padding-bottom:clamp(48px,8vw,120px)!important}
@media(max-width:640px){[data-layout-variant="media-left"],[data-layout-variant="media-right"],[data-layout-variant="inline"]{display:block}}
</style>
""".strip()


@dataclass(frozen=True)
class ComponentFragment:
    name: str
    category: str
    html: str


def sanitize_html(source: str) -> str:
    """Keep uploaded markup useful for preview while never executing supplied code."""
    result = _SCRIPT_PATTERN.sub("", source)
    result = _EMBED_PATTERN.sub("", result)
    result = _VOID_EMBED_PATTERN.sub("", result)
    result = _EVENT_ATTRIBUTE_PATTERN.sub("", result)
    return _JAVASCRIPT_URL_PATTERN.sub(' href="#"', result)


def split_components(
    source: str,
    filename: str,
    *,
    shared_styles: str = "",
    asset_names: dict[str, str] | None = None,
) -> list[ComponentFragment]:
    """Split an uploaded document into its outer horizontal content sections.

    Existing, already-split HTML remains one component. A whole document is split at
    its outer header/section/article/footer boundaries. The original markup remains
    intact inside each fragment so source styling is preserved as far as possible.
    """
    cleaned = sanitize_html(source)
    body_match = _BODY_PATTERN.search(cleaned)
    body = body_match.group("content") if body_match else cleaned
    inline_styles = "\n".join(_STYLE_PATTERN.findall(cleaned))
    body = _STYLE_PATTERN.sub("", body).strip()
    fragments = _outer_sections(body) or [body]
    base_name = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    all_styles = "\n".join(value for value in [inline_styles, shared_styles] if value)
    asset_names = asset_names or {}

    result: list[ComponentFragment] = []
    for index, fragment in enumerate(fragments, start=1):
        if not _meaningful(fragment):
            continue
        name, category = _component_identity(fragment, base_name, index)
        decorated = _decorate_root(
            _rewrite_asset_urls(fragment, asset_names),
            name=name,
            category=category,
            layout_options=_layout_options(category),
        )
        styles = [all_styles, _LAYOUT_RUNTIME_STYLES]
        decorated = "\n".join(value for value in [decorated, *styles] if value)
        result.append(ComponentFragment(name=name, category=category, html=decorated))
    return result


def _outer_sections(source: str) -> list[str]:
    matches = list(_TAG_PATTERN.finditer(source))
    stack: list[tuple[str, int]] = []
    active: tuple[str, int, int] | None = None
    sections: list[str] = []
    for match in matches:
        token = match.group(0)
        tag = match.group(1).casefold()
        closing = token.startswith("</")
        self_closing = token.rstrip().endswith("/>") or tag in _VOID_TAGS
        if closing:
            if not stack:
                continue
            opened_tag, _opened_start = stack.pop()
            if active and opened_tag == active[0] and len(stack) == active[2]:
                sections.append(source[active[1] : match.end()].strip())
                active = None
            continue
        if active is None and tag in _SECTION_TAGS:
            active = (tag, match.start(), len(stack))
        if not self_closing:
            stack.append((tag, match.start()))
    return sections


def _meaningful(fragment: str) -> bool:
    return bool(re.sub(r"<[^>]+>", "", fragment).strip()) or bool(
        re.search(r"<(?:img|picture|video|svg|button|a)\b", fragment, re.IGNORECASE)
    )


def _component_identity(fragment: str, base_name: str, index: int) -> tuple[str, str]:
    lower = fragment.casefold()
    if re.search(r"\b(?:hero|visual|kv|masthead)\b", lower) or "<h1" in lower:
        return "Hero", "hero"
    if re.search(r"\b(?:cta|action|signup|apply|purchase|buy)\b", lower):
        return "CTA", "cta"
    if re.search(r"\b(?:proof|review|testimonial|rating|spec|faq)\b", lower):
        return "Proof", "proof"
    if re.search(r"\b(?:benefit|feature|service|product)\b", lower):
        return "Benefit", "benefit"
    label = base_name or "Content"
    return f"{label.title()} {index}", "content"


def _layout_options(category: str) -> str:
    options = {
        "hero": "source media-left media-right media-top",
        "cta": "source inline centered",
        "proof": "source proof-first cards",
        "benefit": "source media-left media-right stacked",
        "content": "source compact spacious",
    }
    return options.get(category, "source")


def _decorate_root(
    source: str, *, name: str, category: str, layout_options: str
) -> str:
    match = _ROOT_TAG_PATTERN.search(source)
    if not match:
        return (
            f'<section data-component-name="{html.escape(name, quote=True)}" '
            f'data-component-category="{html.escape(category, quote=True)}" '
            f'data-layout-options="{layout_options}">{source}</section>'
        )
    attrs = match.group("attrs")
    additions: list[str] = []
    if "data-component-name" not in attrs:
        additions.append(f'data-component-name="{html.escape(name, quote=True)}"')
    if "data-component-category" not in attrs:
        additions.append(
            f'data-component-category="{html.escape(category, quote=True)}"'
        )
    if "data-layout-options" not in attrs:
        additions.append(f'data-layout-options="{layout_options}"')
    if not additions:
        return source
    replacement = f"<{match.group(1)}{attrs} {' '.join(additions)}>"
    return f"{source[: match.start()]}{replacement}{source[match.end() :]}"


def _rewrite_asset_urls(source: str, asset_names: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = html.unescape(match.group("value"))
        if value.startswith(("asset://", "http://", "https://", "data:", "#", "/")):
            return match.group(0)
        filename = Path(value.split("?", 1)[0]).name
        mapped = asset_names.get(filename)
        if not mapped:
            return match.group(0)
        return f'{match.group("attribute")}"asset://{html.escape(mapped, quote=True)}"'

    return _ASSET_URL_PATTERN.sub(replace, source)
