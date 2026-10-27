"""Sourced Hettich Quadro V6 EB20 profile data."""

HETTICH_PROFILE = {
    "manufacturer": "Hettich",
    "model": "Quadro V6 Silent System, EB20, slide-on",
    "runner_length_mm": 450,
    "left_runner_sku": "9047751",
    "right_runner_sku": "9047752",
    "side_thickness_max_mm": 16,
    "installation_width_per_side_mm": 20,
    "minimum_body_depth_mm": 463,
    "box_length_mm": 450,
    "native_max_load_kg": 30,
    "bottom_underside_recess_mm": {"min": 12, "max": 13},
    "sources": [
        "https://shop.hettich.com/nl_NL/Ladegeleidersystemen/Verborgen-ladegeleiders/Ladegeleiders-Quadro/Quadro-V6/c/group15252148656799",
        "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-450-mm%2C-left/p/9047751",
        "https://shop.hettich.com/us_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-450-mm%2C-right/p/9047752",
        "https://hta.hettich.com/en-de/runner-systems/quadro/quadro-v6",
        "https://www.hettich.com/fileadmin/Media_Center/Catalogue/HAU_Quadro_Runner_15789_en.pdf",
    ],
    "design_allowances": {
        "side_clearance_per_side_mm": 20,
        "box_bottom_recess_mm": "selected within sourced 12-13 mm range",
        "vertical_gap_mm": "project-selected per opening",
        "front_gap_mm": 0,
    },
    "unverified": [
        "minimum and maximum side clearance",
        "vertical runner clearance",
        "mounting details",
        "catch identity and adjustment",
        "load capacity",
    ],
}
HETTICH_PROFILES = {
    380: {
        **HETTICH_PROFILE,
        "runner_length_mm": 380,
        "left_runner_sku": "9047682",
        "right_runner_sku": "9047683",
        "minimum_body_depth_mm": 393,
        "box_length_mm": 380,
        "native_max_load_kg": 25,
        "sources": [
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-380-mm%2C-left/p/9047682",
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-380-mm%2C-right/p/9047683",
        ],
    },
    450: HETTICH_PROFILE,
    480: {
        **HETTICH_PROFILE,
        "runner_length_mm": 480,
        "left_runner_sku": "9047756",
        "right_runner_sku": "9047757",
        "minimum_body_depth_mm": 493,
        "box_length_mm": 480,
        "native_max_load_kg": 30,
        "sources": [
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-480-mm%2C-left/p/9047756",
            "https://shop.hettich.com/gb_EN/Runner-systems/Concealed-drawer-runners/Quadro-drawer-runners/Quadro-V6/Quadro-V6-with-Silent-System%2C-480-mm%2C-right/p/9047757",
            "https://hta.hettich.com/fileadmin/Hettich_Technical_Assistant/PDFs/MTA_929680000_QV6_SFG_SFD_EB20.pdf",
        ],
    },
}
EB20_SLIDE_KEY = "buratino_hettich_quadro_v6_eb20"
EB20_SLIDE_KEYS = {
    380: f"{EB20_SLIDE_KEY}_380",
    450: EB20_SLIDE_KEY,
    480: f"{EB20_SLIDE_KEY}_480",
}
