from pathlib import Path
from string import Template

from app.persona.schemas import PersonaBatch, PersonaKnowledge, PersonaMarkdownFile

_TEMPLATE = Template(
    (Path(__file__).with_name("templates") / "persona.md").read_text(encoding="utf-8")
)


def generate_persona_markdowns(data: PersonaBatch) -> list[PersonaMarkdownFile]:
    return [
        PersonaMarkdownFile(
            filename=f"persona-{chr(96 + index)}.md",
            name=persona.name,
            markdown=_render_persona(persona),
        )
        for index, persona in enumerate(data.personas, start=1)
    ]


def _render_persona(persona: PersonaKnowledge) -> str:
    values = {
        "name": persona.name,
        "profile": _bullets(persona.profile),
        "situation": _bullets(persona.situation),
        "needs": _bullets(persona.needs),
        "pain_points": _bullets(persona.pain_points),
        "interests": _bullets(persona.interests),
        "behaviors": _bullets(persona.behaviors),
        "purchase_journey": _bullets(persona.appendix.purchase_journey),
        "dislikes": _bullets(persona.appendix.dislikes),
    }
    return _TEMPLATE.substitute(values).rstrip() + "\n"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
