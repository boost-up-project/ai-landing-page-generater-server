from pathlib import Path
from string import Template

from app.campaign.schemas import CampaignKnowledge

_EMPTY_CONTENT = "_PDF에서 확인된 정보 없음._"
_TEMPLATE = Template(
    (Path(__file__).with_name("templates") / "campaign.md").read_text(encoding="utf-8")
)


def generate_campaign_markdown(data: CampaignKnowledge) -> str:
    values = {
        field_name: getattr(data, field_name).content.strip() or _EMPTY_CONTENT
        for field_name in type(data).model_fields
    }
    return _TEMPLATE.substitute(values).rstrip() + "\n"
