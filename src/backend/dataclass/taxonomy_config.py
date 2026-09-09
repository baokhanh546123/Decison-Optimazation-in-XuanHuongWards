from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet

@dataclass(frozen=True, slots=True)
class TaxonomyConfig:
    # --- Demand: taxonomy_root -> trọng số p_i và bán kính phủ riêng ---
    taxonomy_root_weight: Dict[str, float] = field(default_factory=lambda: {
        "food_and_drink": 1.0,
        "accommodation": 0.9,
        "arts_and_entertainment": 0.7,
        "retail": 0.6,
        "attractions_and_activities": 0.8,
        "travel_services": 0.5,
        "sports_and_recreation": 0.5,
        "health_and_medicine": 0.3,
        "services_and_business": 0.3,
        "financial_service": 0.2,
        "education": 0.2,
        "public_service_and_government": 0.2,
        "private_establishments_and_corporations": 0.2,
        "structure_and_geography": 0.1,
    })
    default_root_weight: float = 0.3

    taxonomy_root_radius_m: Dict[str, float] = field(default_factory=lambda: {
        "food_and_drink": 300,
        "accommodation": 400,
        "arts_and_entertainment": 500,
        "attractions_and_activities": 800,
        "retail": 300,
        "travel_services": 500,
        "sports_and_recreation": 500,
        "health_and_medicine": 1000,
        "services_and_business": 500,
        "financial_service": 800,
        "education": 800,
        "public_service_and_government": 1000,
        "private_establishments_and_corporations": 500,
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