from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.landing.schemas import EditableImage

PRODUCT_GROUPS = [
    "거실가구",
    "거실수납",
    "침실가구",
    "침실수납",
    "욕실수납",
    "다이닝가구",
    "주방수납",
    "어린이방가구",
    "홈오피스가구",
    "아웃도어가구",
    "현관수납",
    "세탁실정리용품",
]

# Product lines verified against IKEA Korea's current storage category pages.
VERIFIED_PRODUCT_SERIES = {
    "KALLAX 칼락스": "칸형 수납과 공간 분리",
    "BILLY 빌리": "책과 소품 수납",
    "PAX 팍스": "맞춤형 옷장 수납",
    "BESTÅ 베스토": "거실과 TV 주변의 모듈형 수납",
    "EKET 에케트": "벽과 바닥에 자유롭게 구성하는 모듈형 수납",
    "PLATSA 플랏사": "공간에 맞춰 조합하는 옷장 수납",
    "JONAXEL 요낙셀": "침실·주방·현관·욕실·세탁실 오픈 수납",
    "BOAXEL 보악셀": "벽면을 활용하는 오픈 수납",
    "TROFAST 트로파스트": "어린이용 장난감 수납",
    "IVAR 이바르": "조합 가능한 선반 수납",
    "OMAR 오마르": "오픈 선반 수납",
    "SMÅSTAD 스모스타드": "어린이방 수납",
}

ROOM_KEYWORDS = {
    "living_room": ["거실", "소파", "수납", "TV", "휴식", "가족", "라운지"],
    "bedroom": ["침실", "수면", "침대", "옷장", "드레스룸", "정리"],
    "bathroom": ["욕실", "화장실", "세면", "타월", "욕실수납"],
    "dining": ["다이닝", "식탁", "의자", "식사", "홈파티"],
    "childrens_room": ["아이", "어린이", "놀이", "학습", "가족"],
    "kitchen": ["주방", "요리", "조리", "식기", "팬트리", "주방수납"],
    "home_office": ["업무", "책상", "집중", "서재", "홈오피스", "재택"],
    "outdoor": ["야외", "테라스", "발코니", "정원", "아웃도어"],
    "hallway": ["현관", "신발", "외출", "복도", "입구"],
    "laundry": ["세탁", "빨래", "세탁실", "정리"],
}

COMPONENT_HINTS = {
    "hero": ["hero", "banner"],
    "cta": ["banner", "teaser"],
    "content": ["bento", "editorial", "teaser"],
    "benefit": ["bento", "editorial"],
    "proof": ["carousel", "editorial"],
    "기본": ["bento", "teaser", "editorial"],
}


@dataclass(frozen=True)
class IkeaImage:
    id: str
    cdn_url: str
    alt_text: str
    context_text: str
    image_type: str
    recommended_component: str
    room: str
    category: str


def load_ikea_images(settings: Settings) -> list[IkeaImage]:
    path = settings.storage_root / "uploads" / "ikea_metadata_300_v2.json"
    if not path.is_file():
        return []
    return _parse_images(path)


def ikea_prompt_context(images: list[IkeaImage]) -> dict[str, Any]:
    rooms = sorted({item.room for item in images if item.room})
    categories = sorted({item.category for item in images if item.category})
    recommended_components = sorted(
        {item.recommended_component for item in images if item.recommended_component}
    )
    return {
        "available_product_group_level_only": PRODUCT_GROUPS,
        "verified_product_series": VERIFIED_PRODUCT_SERIES,
        "available_image_rooms": rooms,
        "available_image_categories": categories,
        "available_recommended_components": recommended_components,
        "product_name_warning": (
            "Use only names in verified_product_series. Never invent another IKEA "
            "series or imply that the selected image depicts that series."
        ),
    }


def assign_ikea_images(
    image_values: list[EditableImage],
    *,
    copy_values: list[str],
    persona: dict[str, Any],
    component_name: str,
    component_category: str,
    image_pool: list[IkeaImage],
    used_image_ids: set[str],
) -> list[EditableImage]:
    if not image_pool or not image_values:
        return image_values
    assigned: list[EditableImage] = []
    for index, value in enumerate(image_values):
        query = " ".join(
            [
                component_name,
                component_category,
                " ".join(copy_values),
                _persona_text(persona),
                value.alt,
            ]
        )
        image = _select_image(
            query,
            component_category=component_category,
            image_pool=image_pool,
            used_image_ids=used_image_ids,
            image_index=index,
        )
        if image is None:
            assigned.append(value)
            continue
        used_image_ids.add(image.id)
        assigned.append(
            EditableImage(
                asset_filename=image.cdn_url,
                alt=_alt_text(image, fallback=value.alt),
            )
        )
    return assigned


def _parse_images(path: Path) -> list[IkeaImage]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    images: list[IkeaImage] = []
    for item in raw if isinstance(raw, list) else []:
        image = item.get("image") or {}
        classification = item.get("classification") or {}
        cdn_url = str(image.get("cdn_url") or "")
        if not cdn_url:
            continue
        images.append(
            IkeaImage(
                id=str(item.get("id") or cdn_url),
                cdn_url=cdn_url,
                alt_text=str(image.get("alt_text") or ""),
                context_text=str(image.get("context_text") or ""),
                image_type=str(image.get("image_type") or ""),
                recommended_component=str(image.get("recommended_component") or ""),
                room=str(classification.get("room") or ""),
                category=str(classification.get("category") or ""),
            )
        )
    return images


def _select_image(
    query: str,
    *,
    component_category: str,
    image_pool: list[IkeaImage],
    used_image_ids: set[str],
    image_index: int,
) -> IkeaImage | None:
    query_normalized = query.casefold()
    preferred_components = COMPONENT_HINTS.get(
        component_category.casefold(),
        COMPONENT_HINTS.get(component_category, []),
    )
    scored = [
        (_score_image(item, query_normalized, preferred_components, used_image_ids), item)
        for item in image_pool
    ]
    scored = [(score, item) for score, item in scored if score > 0]
    if not scored:
        fallback = [
            item for item in image_pool if item.id not in used_image_ids
        ] or image_pool
        return fallback[image_index % len(fallback)] if fallback else None
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    return scored[0][1]


def _score_image(
    image: IkeaImage,
    query: str,
    preferred_components: list[str],
    used_image_ids: set[str],
) -> int:
    score = 0
    if image.id in used_image_ids:
        score -= 8
    if image.recommended_component in preferred_components:
        score += 7
    if image.image_type == "roomset":
        score += 2
    if image.room:
        for keyword in ROOM_KEYWORDS.get(image.room, []):
            if keyword.casefold() in query:
                score += 5
    for token in _tokens(image.context_text + " " + image.category + " " + image.room):
        if token and token in query:
            score += 1
    return score


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in re.split(r"[^0-9A-Za-z가-힣_]+", value) if token]


def _persona_text(persona: dict[str, Any]) -> str:
    data = persona.get("data") if isinstance(persona, dict) else {}
    return json.dumps(data or persona, ensure_ascii=False)


def _alt_text(image: IkeaImage, *, fallback: str) -> str:
    if image.context_text:
        return f"IKEA {image.context_text}"
    if image.alt_text and image.alt_text.casefold() != "image":
        return image.alt_text
    return fallback or "IKEA 공간 이미지"
