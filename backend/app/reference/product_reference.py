"""
Static SEVIRI channel + composite reference content (BUILDPLAN §9 / §14).

Seeded once at startup. Real domain descriptions — not placeholders.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ProductReference
from app.processing.composite_catalog import COMPOSITE_LABELS, COMPOSITE_NAMES

# Solar-dependent channels (missing/empty at night for the imaged region)
SOLAR_DEPENDENT_CHANNELS = frozenset({"HRV", "VIS006", "VIS008", "IR_016"})

CHANNEL_NAMES = [
    "HRV",
    "VIS006",
    "VIS008",
    "IR_016",
    "IR_039",
    "WV_062",
    "WV_073",
    "IR_087",
    "IR_097",
    "IR_108",
    "IR_120",
    "IR_134",
]

PRODUCT_REFERENCE_SEED: list[dict] = [
    {
        "product_name": "HRV",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "0.6–0.9 µm broadband (High Resolution Visible)",
        "approximate_resolution": "~1 km at SSP",
        "plain_language_description": (
            "The High Resolution Visible channel is a broadband visible sensor that shows "
            "reflected sunlight at roughly twice the spatial detail of the other SEVIRI "
            "visible channels. Bright areas are thick clouds or snow; darker areas are "
            "clear land or ocean. It only contains useful data in daylight."
        ),
        "agriculture_application": (
            "Helps map cloud cover over farmland at fine scale so irrigation and spraying "
            "windows can be timed around clear periods."
        ),
        "aviation_application": (
            "Supports visual cloud-top and fog checks where high spatial detail matters "
            "near airports and mountain ridges during daytime."
        ),
        "natural_resource_application": (
            "Useful for spotting fire smoke and surface brightening (e.g. snow/ice extent) "
            "when sunlight is available."
        ),
        "disaster_response_application": (
            "Daytime situational awareness for flooding or storm damage where cloud "
            "patterns must be resolved at ~1 km detail."
        ),
    },
    {
        "product_name": "VIS006",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "0.6 µm visible (red)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "VIS006 measures reflected red sunlight. It is a classic cloud and surface "
            "channel: thick clouds appear bright; vegetation and water appear darker. "
            "Like all pure visible channels, it is blank or unusable at night."
        ),
        "agriculture_application": (
            "Cloud mapping over cropland and rough sense of surface brightness contrasts "
            "relevant to vegetation monitoring during the day."
        ),
        "aviation_application": (
            "Daytime cloud identification and rough optical-thickness cues for VFR-type "
            "situational awareness."
        ),
        "natural_resource_application": (
            "Baseline reflectance for land/water discrimination and dust plumes when "
            "paired with near-IR channels."
        ),
        "disaster_response_application": (
            "Quick daytime overview of storm cloud fields after a severe-weather event."
        ),
    },
    {
        "product_name": "VIS008",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "0.8 µm visible / near-IR",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "VIS008 sits in the near-infrared where healthy vegetation reflects strongly. "
            "Clouds remain bright; vegetated land is brighter than in VIS006, which helps "
            "separate vegetation from bare soil when comparing the two visible channels."
        ),
        "agriculture_application": (
            "Vegetation contrast versus bare soil supports crop condition and drought "
            "screening when combined with VIS006."
        ),
        "aviation_application": (
            "Additional daytime cloud/surface contrast, especially where vegetation "
            "complicates VIS006-only interpretation."
        ),
        "natural_resource_application": (
            "Used with VIS006 for land-cover contrast and burn-scar / smoke context "
            "in daylight images."
        ),
        "disaster_response_application": (
            "Helps distinguish flooded dark water from vegetated land under daylight "
            "conditions."
        ),
    },
    {
        "product_name": "IR_016",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "1.6 µm near-infrared (solar)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_016 is a solar near-IR channel sensitive to particle size and phase. "
            "Ice clouds and snow often appear darker than water clouds of the same "
            "optical thickness. It requires sunlight and is unavailable at night."
        ),
        "agriculture_application": (
            "Daytime discrimination of ice vs water cloud helps anticipate frost or "
            "hail-bearing systems over agricultural regions."
        ),
        "aviation_application": (
            "Ice/water cloud phase cues support icing-hazard awareness during daytime "
            "operations."
        ),
        "natural_resource_application": (
            "Snow/ice vs cloud discrimination on mountains and high plateaus in daylight."
        ),
        "disaster_response_application": (
            "Supports daytime assessment of storm systems with mixed-phase cloud tops."
        ),
    },
    {
        "product_name": "IR_039",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "3.9 µm shortwave infrared",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_039 sees both thermal emission and some reflected solar energy by day. "
            "At night it is used for fog and low-cloud detection (often with IR_108). "
            "Very hot surfaces such as fires also stand out as bright/hot pixels."
        ),
        "agriculture_application": (
            "Nighttime fog and low-stratus detection protects against frost/fog impacts "
            "on crops when paired with IR window channels."
        ),
        "aviation_application": (
            "Critical for fog and low-cloud detection near airports, especially at night "
            "and around dawn/dusk."
        ),
        "natural_resource_application": (
            "Hotspot detection for wildfires and industrial flares in clear conditions."
        ),
        "disaster_response_application": (
            "Locates active fire fronts and supports smoke-plume context with other channels."
        ),
    },
    {
        "product_name": "WV_062",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "6.2 µm water vapour (upper troposphere)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "WV_062 senses mid-to-upper tropospheric moisture. Moist regions appear "
            "colder/brighter in typical WV displays; dry slots appear warmer/darker. "
            "It works day and night because it measures thermal emission in a water-vapour band."
        ),
        "agriculture_application": (
            "Tracks large-scale dry air and moisture advection that drive multi-day "
            "rainfall or drying trends affecting crops."
        ),
        "aviation_application": (
            "Highlights jet-stream dry slots and upper-level waves relevant to "
            "turbulence forecasting."
        ),
        "natural_resource_application": (
            "Monitors moisture pathways that influence regional drought or recharge patterns."
        ),
        "disaster_response_application": (
            "Shows dry-air intrusions that can organize severe convection or intensify "
            "tropical systems."
        ),
    },
    {
        "product_name": "WV_073",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "7.3 µm water vapour (mid troposphere)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "WV_073 is sensitive to mid-tropospheric water vapour, a little lower in the "
            "atmosphere than WV_062. Comparing the two WV channels reveals the vertical "
            "structure of moist and dry layers. Available day and night."
        ),
        "agriculture_application": (
            "Indicates whether mid-level moisture is feeding overnight storms over "
            "growing regions."
        ),
        "aviation_application": (
            "Supports analysis of mid-level moisture and cloud layers for en-route "
            "weather briefing."
        ),
        "natural_resource_application": (
            "Helps interpret rainfall potential when combined with IR window channels."
        ),
        "disaster_response_application": (
            "Used with WV_062 to diagnose moisture depth ahead of floods or flash-flood "
            "events."
        ),
    },
    {
        "product_name": "IR_087",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "8.7 µm infrared window / dust-sensitive",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_087 sits near an atmospheric window but is partly used for dust and "
            "cloud-phase discrimination when differenced with longer-wave IR channels. "
            "It provides cloud-top and surface brightness-temperature information day and night."
        ),
        "agriculture_application": (
            "Contributes to dust-over-cropland detection when used in dust RGB products."
        ),
        "aviation_application": (
            "Supports dust-storm and volcanic-ash discrimination via multi-channel "
            "differences used in aviation hazard products."
        ),
        "natural_resource_application": (
            "Part of the split-window/dust toolkit for arid-land monitoring."
        ),
        "disaster_response_application": (
            "Helps map dust outbreaks that reduce visibility and air quality after "
            "drought or storm events."
        ),
    },
    {
        "product_name": "IR_097",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "9.7 µm ozone / upper-atmosphere IR",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_097 is influenced by atmospheric ozone absorption and upper-level "
            "thermal structure. In operational RGBs it contributes to airmass and "
            "stratospheric intrusion signals rather than being used alone as a simple "
            "picture of clouds."
        ),
        "agriculture_application": (
            "Indirectly supports large-scale weather pattern interpretation that drives "
            "multi-day farm forecasts."
        ),
        "aviation_application": (
            "Used in airmass RGB products that highlight tropopause folds and "
            "jet-related features relevant to clear-air turbulence."
        ),
        "natural_resource_application": (
            "Supports synoptic environmental analysis rather than direct surface mapping."
        ),
        "disaster_response_application": (
            "Helps analysts locate dynamically active upper-air features accompanying "
            "severe weather."
        ),
    },
    {
        "product_name": "IR_108",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "10.8 µm infrared window",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_108 is the primary thermal infrared window channel. Colder (high) clouds "
            "appear brighter in common IR displays; warmer surfaces appear darker. "
            "It works equally well day and night and is the backbone of storm-top monitoring."
        ),
        "agriculture_application": (
            "Cloud-top temperature history guides severe-storm and hail risk awareness "
            "over farmland."
        ),
        "aviation_application": (
            "Standard channel for convective cell identification, anvil outlines, and "
            "nighttime cloud monitoring."
        ),
        "natural_resource_application": (
            "Surface brightness temperatures under clear skies support heat anomaly "
            "and cold-outbreak monitoring."
        ),
        "disaster_response_application": (
            "Tracks cold overshooting tops and mature convective systems during "
            "flood and severe-storm responses."
        ),
    },
    {
        "product_name": "IR_120",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "12.0 µm infrared window",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_120 is a second longwave window channel. Differencing IR_108 and IR_120 "
            "(split window) helps detect thin cirrus, dust, and some low-level features "
            "that a single channel can miss. Available day and night."
        ),
        "agriculture_application": (
            "Split-window dust and moisture cues help anticipate dust that can stress "
            "crops and livestock."
        ),
        "aviation_application": (
            "Used with IR_108 for dust and ash detection products that protect "
            "en-route and terminal operations."
        ),
        "natural_resource_application": (
            "Surface emissivity/temperature contrasts under clear skies contribute to "
            "land-surface monitoring."
        ),
        "disaster_response_application": (
            "Supports mapping of volcanic ash and mineral dust after eruptions or "
            "severe wind events."
        ),
    },
    {
        "product_name": "IR_134",
        "product_kind": "channel",
        "wavelength_or_spectral_band": "13.4 µm CO₂ absorption IR",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "IR_134 is influenced by carbon dioxide absorption and is used for "
            "cloud-top height / atmospheric sounding style products. In RGB composites "
            "it helps separate high cloud from mid-level cloud. Day and night capable."
        ),
        "agriculture_application": (
            "Indirectly supports storm-height interpretation relevant to hail risk "
            "forecasting for crops."
        ),
        "aviation_application": (
            "Contributes to cloud-height and airmass products used in en-route "
            "weather analysis."
        ),
        "natural_resource_application": (
            "Supports layered atmospheric interpretation rather than direct surface "
            "resource mapping."
        ),
        "disaster_response_application": (
            "Helps classify how deep convective systems are during flood and cyclone "
            "monitoring."
        ),
    },
    {
        "product_name": "natural_color",
        "product_kind": "composite",
        "wavelength_or_spectral_band": "RGB from VIS006 / VIS008 / IR_016 (approx.)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "Natural colour (also called True Color–like) blends solar reflectance "
            "channels so vegetation appears greenish, deserts brownish, and thick "
            "clouds white. It is intuitive for presentations but only works while "
            "sunlight illuminates the disk — nighttime timeslots will show it as "
            "unavailable (night)."
        ),
        "agriculture_application": (
            "Quick daylight overview of cloud vs crop regions for field operations planning."
        ),
        "aviation_application": (
            "Human-friendly daytime situational picture of cloud fields for briefings."
        ),
        "natural_resource_application": (
            "Easy-to-read daytime map of land, water, and cloud for environmental updates."
        ),
        "disaster_response_application": (
            "Communicates storm and cloud extent to non-specialists during daylight events."
        ),
    },
    {
        "product_name": "airmass",
        "product_kind": "composite",
        "wavelength_or_spectral_band": "RGB using WV + ozone/IR differences (EUMETSAT airmass)",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "The airmass RGB highlights warm/cold airmasses, moist vs dry upper air, "
            "and jet-related features. Reddish/orange areas often indicate dry descending "
            "air or ozone-rich stratospheric intrusions; blues/greens relate to moist "
            "tropical air. It works day and night."
        ),
        "agriculture_application": (
            "Shows large-scale airmass changes that drive multi-day temperature and "
            "rainfall swings over farmland."
        ),
        "aviation_application": (
            "Widely used to spot jet streaks, tropopause folds, and clear-air turbulence "
            "environments."
        ),
        "natural_resource_application": (
            "Tracks synoptic moisture regimes that influence regional water availability."
        ),
        "disaster_response_application": (
            "Helps anticipate rapidly deepening systems and dry-air surge behavior."
        ),
    },
    {
        "product_name": "dust",
        "product_kind": "composite",
        "wavelength_or_spectral_band": "RGB from IR_087 / IR_108 / IR_120 differences",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "The dust RGB is designed so airborne mineral dust often appears pink/magenta "
            "against a blueish clear scene, while thick ice clouds appear reddish. "
            "It is especially useful over deserts and works day and night (with "
            "interpretation differences)."
        ),
        "agriculture_application": (
            "Flags dust plumes that can bury crops, reduce sunlight, and damage "
            "irrigation equipment."
        ),
        "aviation_application": (
            "Operationally critical for dust-storm visibility hazards along flight routes "
            "and at desert airports."
        ),
        "natural_resource_application": (
            "Monitors dust mobilization from dry lakebeds and arid soil surfaces."
        ),
        "disaster_response_application": (
            "Maps haboobs and post-drought dust outbreaks affecting health and transport."
        ),
    },
    {
        "product_name": "ash",
        "product_kind": "composite",
        "wavelength_or_spectral_band": "RGB optimized for volcanic ash vs ice cloud",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "The ash RGB separates volcanic ash (often reddish/yellow tones in EUMETSAT "
            "style products) from ice clouds and ordinary water clouds using IR "
            "channel differences. Day and night capable; interpretation still needs "
            "care near thick convection."
        ),
        "agriculture_application": (
            "Tracks ashfall risk to soils, livestock water, and greenhouse films near "
            "volcanoes."
        ),
        "aviation_application": (
            "Primary satellite cue for volcanic ash avoidance — engines and airframes "
            "are highly vulnerable to ash."
        ),
        "natural_resource_application": (
            "Documents ash dispersal pathways after eruptions for environmental impact "
            "assessment."
        ),
        "disaster_response_application": (
            "Guides evacuation and airspace closures during volcanic crises."
        ),
    },
    {
        "product_name": "convection",
        "product_kind": "composite",
        "wavelength_or_spectral_band": "RGB highlighting deep convection / overshooting tops",
        "approximate_resolution": "~3 km at SSP",
        "plain_language_description": (
            "The convection RGB emphasizes growing and mature thunderstorms, often "
            "making the coldest overshooting tops visually distinct. It is used to "
            "quickly find the most intense cells in a storm complex, day or night "
            "(ingredients vary by solar vs IR-dominated recipes)."
        ),
        "agriculture_application": (
            "Identifies hail- and wind-bearing cells before they reach cropland."
        ),
        "aviation_application": (
            "Supports rerouting around intense convective cores and anvil blow-off."
        ),
        "natural_resource_application": (
            "Locates storms likely to drive flash runoff into reservoirs and catchments."
        ),
        "disaster_response_application": (
            "Priority product during flash-flood and severe thunderstorm responses."
        ),
    },
    {
        "product_name": "final_globe_mix",
        "product_kind": "summary",
        "wavelength_or_spectral_band": "Role-aware multi-product blend (hero + accents)",
        "approximate_resolution": "Resampled whole-disk preview (~1.5 km display grid)",
        "plain_language_description": (
            "Final Globe Mix is a presentation summary: one whole-disk image per sampled "
            "timeslot. A role-matched hero product (natural colour by day, airmass at "
            "twilight, night microphysics / IR at night) is blended with a few accent "
            "products so day, twilight, and night cards stay visually distinct. It is not "
            "a new satellite measurement — it is a visual overview of that timeslot."
        ),
        "agriculture_application": (
            "Quick at-a-glance disk overview when briefing cloud or dust conditions "
            "without opening every individual product."
        ),
        "aviation_application": (
            "Demo-friendly whole-disk context before drilling into airmass, dust, or "
            "convection products for a specific timeslot."
        ),
        "natural_resource_application": (
            "Shows how land/ocean/cloud contrast shifts across the sample roles on one card."
        ),
        "disaster_response_application": (
            "Useful as a poster/overview frame for a timeslot during presentations, then "
            "link through to the detailed product gallery."
        ),
    },
]


def _auto_composite_seeds() -> list[dict]:
    """Fill glossary rows for any catalogue composite missing a hand-written seed."""
    existing = {r["product_name"] for r in PRODUCT_REFERENCE_SEED}
    out: list[dict] = []
    for name in COMPOSITE_NAMES:
        if name in existing:
            continue
        label = COMPOSITE_LABELS.get(name, name.replace("_", " ").title())
        out.append(
            {
                "product_name": name,
                "product_kind": "composite",
                "wavelength_or_spectral_band": f"RGB composite ({label})",
                "approximate_resolution": "~3 km at SSP (HRV-based products resampled to IR grid)",
                "plain_language_description": (
                    f"{label} is a public satpy / EUMETSAT-style MSG SEVIRI RGB composite "
                    "built from the standard SEVIRI channels. It highlights meteorological "
                    "features (clouds, dust, airmass, convection, fog, etc.) depending on "
                    "the recipe. Daylight-only recipes are marked unavailable at night."
                ),
                "agriculture_application": (
                    "Supports situational awareness of cloud, dust, and storm conditions "
                    "that affect field operations and irrigation timing."
                ),
                "aviation_application": (
                    "Provides a quick visual layer for hazardeous weather, dust, ash, or "
                    "convective cores along routes and near terminals."
                ),
                "natural_resource_application": (
                    "Helps monitor regional atmospheric and land-surface conditions "
                    "relevant to water, range, and forest management."
                ),
                "disaster_response_application": (
                    "Useful overview layer during severe weather, dust storms, volcanic "
                    "ash, or flood-producing convective events."
                ),
            }
        )
    return out


def seed_product_reference(db: Session) -> int:
    """Insert missing product_reference rows. Returns number of rows inserted."""
    inserted = 0
    for row in PRODUCT_REFERENCE_SEED + _auto_composite_seeds():
        existing = db.get(ProductReference, row["product_name"])
        if existing is None:
            db.add(ProductReference(**row))
            inserted += 1
    db.commit()
    return inserted