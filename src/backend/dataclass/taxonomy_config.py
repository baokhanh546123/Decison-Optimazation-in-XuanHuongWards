from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet

@dataclass(frozen=True, slots=True)
class TaxonomyConfig:
    # --- Demand: taxonomy_root -> trọng số p_i và bán kính phủ riêng ---
    # Mỗi taxonomy có weight + radius_m để UI/solver điều chỉnh bán kính theo loại.
    taxonomy_root_weight: Dict[str, float] = field(default_factory=lambda: {
        "food_and_drink": 1.0,
        "lodging": 0.9,
        "accommodation": 0.9,
        "shopping": 0.6,
        "retail": 0.6,
        "arts_and_entertainment": 0.7,
        "attractions_and_activities": 0.8,
        "cultural_and_historic": 0.5,
        "sports_and_recreation": 0.5,
        "travel_and_transportation": 0.5,
        "travel_services": 0.5,
        "lifestyle_services": 0.4,
        "services_and_business": 0.3,
        "health_and_medicine": 0.3,
        "health_care": 0.3,
        "education": 0.2,
        "community_and_government": 0.2,
        "public_service_and_government": 0.2,
        "financial_service": 0.2,
        "private_establishments_and_corporations": 0.2,
        "geographic_entities": 0.1,
        "structure_and_geography": 0.1,
    })
    default_root_weight: float = 0.3

    # Bán kính phủ mặc định (m) theo taxonomy — UI slider sync từ đây / từ candidate.radius_m
    taxonomy_root_radius_m: Dict[str, float] = field(default_factory=lambda: {
        "food_and_drink": 300,
        "lodging": 400,
        "accommodation": 400,
        "shopping": 300,
        "retail": 300,
        "arts_and_entertainment": 500,
        "attractions_and_activities": 800,
        "cultural_and_historic": 500,
        "sports_and_recreation": 500,
        "travel_and_transportation": 500,
        "travel_services": 500,
        "lifestyle_services": 500,
        "services_and_business": 500,
        "health_and_medicine": 1000,
        "health_care": 1000,
        "education": 800,
        "community_and_government": 1000,
        "public_service_and_government": 1000,
        "financial_service": 800,
        "private_establishments_and_corporations": 500,
        "geographic_entities": 500,
        "structure_and_geography": 500,
    })
    default_radius_m: float = 500
    min_confidence: float = 0.3

    # --- Candidate/road: class -> cost rank, class bị loại/ưu tiên thấp ---
    candidate_excluded_class: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"motorway", "trunk", "standard_gauge"})
    )
    candidate_low_priority_class: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"steps", "path", "track"})
    )
    class_cost_rank: Dict[str, float] = field(default_factory=lambda: {
        "primary": 5.0, "secondary": 4.0, "tertiary": 3.0,
        "residential": 2.0, "living_street": 2.0, "pedestrian": 2.0,
        "unclassified": 1.5, "service": 1.0, "footway": 1.0,
        "path": 0.5, "track": 0.5, "steps": 0.5,
    })


# Instance mặc định — import cái này ở utils/ thay vì định nghĩa lại dict rời rạc,
# nếu/khi bạn muốn tham số hoá thay vì hardcode global.
DEFAULT_TAXONOMY_CONFIG = TaxonomyConfig()
