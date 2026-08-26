from __future__ import annotations

from pathlib import Path
from string import Template

from app.brand.schemas import BrandKnowledge, ReviewSection

_EMPTY_CONTENT = "_PDF에서 확인된 정보 없음._"
_TEMPLATE = Template(
    (Path(__file__).with_name("templates") / "brand.md").read_text(encoding="utf-8")
)


def generate_brand_markdown(data: BrandKnowledge) -> str:
    values: dict[str, str] = {}
    for group in (
        data.brand_identity,
        data.verbal_guideline,
        data.visual_guideline,
    ):
        for field_name in type(group).model_fields:
            section: ReviewSection = getattr(group, field_name)
            values[field_name] = section.content.strip() or _EMPTY_CONTENT

    return _TEMPLATE.substitute(values).rstrip() + "\n"
