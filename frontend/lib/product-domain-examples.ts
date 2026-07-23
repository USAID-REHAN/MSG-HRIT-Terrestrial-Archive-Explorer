export type DomainKey =
  | "agriculture"
  | "aviation"
  | "natural_resources"
  | "disaster_response";

function exampleSet(
  agriculture: string,
  aviation: string,
  naturalResources: string,
  disasterResponse: string
): Record<DomainKey, string> {
  return {
    agriculture,
    aviation,
    natural_resources: naturalResources,
    disaster_response: disasterResponse,
  };
}

const DEFAULT_EXAMPLES = exampleSet(
  "Example: A farm advisory team checks the latest full-disk imagery before planning irrigation, spraying, or harvest work around incoming cloud and dust.",
  "Example: An airport weather desk reviews the imagery before arrivals and departures to spot cloud shields, dust, or convective development near approach corridors.",
  "Example: A regional environment unit compares successive images to monitor dust movement, cloud cover, and broad land-surface conditions over river basins and drylands.",
  "Example: An emergency operations center uses the imagery as a rapid visual brief to understand where storms, dust, or thick cloud are expanding before issuing field updates."
);

const PRODUCT_EXAMPLES: Record<string, Record<DomainKey, string>> = {
  HRV: exampleSet(
    "Example: An agronomy team uses HRV during daylight to judge small-scale cloud shadows over irrigated fields before scheduling spraying.",
    "Example: Tower meteorologists use HRV to track fine low-cloud edges and growing cumulus near an airport in the afternoon.",
    "Example: Water managers inspect HRV for detailed cloud structure over mountain catchments feeding reservoirs.",
    "Example: Flood responders use HRV to watch the texture and spread of storm tops over a threatened district in near real time."
  ),
  VIS006: exampleSet(
    "Example: Crop analysts use VIS 0.6 to separate bright cloud from darker land so they can see whether a planting zone will stay sunlit through the morning.",
    "Example: Flight dispatchers use VIS 0.6 in daytime to review the areal extent of cloud fields along a domestic route.",
    "Example: Land agencies use VIS 0.6 to watch broad dust plumes spreading off dry terrain.",
    "Example: Response teams use VIS 0.6 as a quick daylight overview after a storm outbreak to see the remaining cloud shield."
  ),
  VIS008: exampleSet(
    "Example: Agriculture teams compare VIS 0.8 scenes through the day to see where haze or shallow cloud may reduce solar input over cropland.",
    "Example: Airport forecasters use VIS 0.8 to follow cloud sheets and haze feeding into terminal airspace during daylight.",
    "Example: Environmental officers use VIS 0.8 to distinguish land, water, and bright cloud over coastal or inland basins.",
    "Example: Disaster cells use VIS 0.8 to map the daytime spread of residual smoke or dust after a damaging event."
  ),
  IR_016: exampleSet(
    "Example: Field planners use IR 1.6 to better separate water cloud and snow-contaminated terrain when morning operations depend on local cloud cover.",
    "Example: Aviation meteorologists use IR 1.6 in daylight to refine low cloud and icing-related cloud interpretation near airports.",
    "Example: Snow and glacier observers use IR 1.6 to help distinguish snow/ice from cloud over high terrain.",
    "Example: Mountain response teams use IR 1.6 when they need a clearer daytime view of snow-covered areas after avalanches or severe weather."
  ),
  IR_039: exampleSet(
    "Example: Agricultural fire-watch teams use IR 3.9 at night to flag unusually hot pixels from crop-residue burning near farmland.",
    "Example: Aviation desks use IR 3.9 at night to identify fog-prone low cloud and localized hotspots that may affect visibility assessments.",
    "Example: Forestry officers use IR 3.9 to detect wildfire hotspots before sunrise when visible channels are unavailable.",
    "Example: Emergency responders use IR 3.9 overnight to monitor active fire fronts or industrial hot spots during a crisis."
  ),
  WV_062: exampleSet(
    "Example: Farm risk analysts use WV 6.2 to monitor upper-level moisture surges that may signal a shift toward unsettled weather over crops.",
    "Example: Aviation forecasters use WV 6.2 to track dry intrusions and jet-related upper-air patterns affecting route weather.",
    "Example: Basin-scale planners use WV 6.2 to watch moisture transport feeding major cloud systems.",
    "Example: Disaster managers use WV 6.2 to understand the upper-air setup behind a rapidly organizing storm system."
  ),
  WV_073: exampleSet(
    "Example: Agriculture services use WV 7.3 to monitor mid-level moisture pushing toward farming districts ahead of rain events.",
    "Example: En-route forecasters use WV 7.3 to assess mid-tropospheric moisture and subsidence near air corridors.",
    "Example: Environmental teams use WV 7.3 to compare moisture structure across large dryland and coastal regions.",
    "Example: Emergency meteorologists use WV 7.3 to judge whether a storm environment is becoming more supportive of heavy rain."
  ),
  IR_087: exampleSet(
    "Example: Agriculture offices use IR 8.7 within dust-sensitive interpretation to see if airborne dust may stress crops and machinery.",
    "Example: Aviation teams use IR 8.7 as part of dust and ash discrimination when visibility hazards threaten routes or terminals.",
    "Example: Environmental agencies use IR 8.7 to watch dust lifted from dry soils and lakebeds.",
    "Example: Disaster centers use IR 8.7 when dust outbreaks or volcanic contamination reduce surface visibility and disrupt transport."
  ),
  IR_097: exampleSet(
    "Example: Agricultural weather analysts use IR 9.7 as part of upper-level moisture and ozone-sensitive interpretation ahead of strong weather shifts.",
    "Example: Flight planning teams use IR 9.7 within airmass analysis to understand tropopause-level structure affecting high-altitude routing.",
    "Example: Atmosphere-monitoring groups use IR 9.7 to study large-scale upper-air composition and structure.",
    "Example: Crisis forecasters use IR 9.7 inside airmass products to diagnose the broader environment around major storms."
  ),
  IR_108: exampleSet(
    "Example: Agriculture advisors use IR 10.8 overnight to monitor cloud-top temperatures and lingering storm anvils over cropland.",
    "Example: Aviation operations use IR 10.8 continuously to track deep cloud, fog, and storm tops affecting airports and airways.",
    "Example: Natural-resource analysts use IR 10.8 to map cloud cover over catchments and arid land even after sunset.",
    "Example: Emergency teams use IR 10.8 through the night to follow cold cloud tops associated with severe storms or heavy rain."
  ),
  IR_120: exampleSet(
    "Example: Farm-support services use split-window cues involving IR 12.0 to watch for dust and low-level moisture changes over dry cropland.",
    "Example: Aviation desks use IR 12.0 with IR 10.8 for dust and ash discrimination before routing decisions.",
    "Example: Environmental units use IR 12.0 to monitor dust and surface-emissivity differences across deserts and dry basins.",
    "Example: Disaster responders use IR 12.0 products to track dust storms or volcanic ash clouds affecting communities and transport."
  ),
  IR_134: exampleSet(
    "Example: Agricultural forecasters use IR 13.4 to understand high cloud and upper-level structure before major weather changes over farms.",
    "Example: Aviation meteorologists use IR 13.4 in cloud-height interpretation for route-level hazard awareness.",
    "Example: Natural-resource planners use IR 13.4 to separate very high cloud influence from lower-level surface-related patterns.",
    "Example: Response teams use IR 13.4 during severe weather analysis to identify the depth and organization of major cloud systems."
  ),
  natural_color: exampleSet(
    "Example: A crop consultant uses the natural-colour RGB in daytime to brief farmers on where thick cloud is shading cotton or wheat belts.",
    "Example: An airline weather desk uses the natural-colour RGB to give pilots a familiar-looking daytime view of cloud cover near departure airports.",
    "Example: A watershed team uses natural-colour imagery to distinguish cloud, land, and water across reservoirs and surrounding terrain.",
    "Example: A provincial emergency center uses natural-colour imagery for a quick daylight situation picture after a severe storm day."
  ),
  airmass: exampleSet(
    "Example: Agriculture forecasters use the Air Mass RGB to explain why a cooler, drier upper-air intrusion may trigger unstable weather over cropland tomorrow.",
    "Example: Aviation meteorologists use the Air Mass RGB to identify jet-related dry intrusions and tropopause folds along long-haul routes.",
    "Example: Environmental analysts use the Air Mass RGB to study synoptic-scale air-mass boundaries over deserts, mountains, and seas.",
    "Example: Disaster teams use the Air Mass RGB to understand the large-scale environment feeding a widespread severe-weather outbreak."
  ),
  dust: exampleSet(
    "Example: Agricultural agencies use the Dust RGB to warn farmers when a dust plume is moving toward fields and could damage seedlings or reduce sunlight.",
    "Example: Aviation operations use the Dust RGB to monitor visibility-reducing plumes crossing approach paths and regional air corridors.",
    "Example: Natural-resource departments use the Dust RGB to track dust mobilization from dry riverbeds, lakebeds, and exposed soils.",
    "Example: Emergency managers use the Dust RGB during a haboob to map the plume edge and prioritize transport and health advisories."
  ),
  ash: exampleSet(
    "Example: Agricultural extension teams use the Ash RGB to distinguish ash-like aerosol contamination from normal cloud when advising exposed farming areas.",
    "Example: Volcanic ash advisory units use the Ash RGB directly to identify ash clouds that could endanger jet engines.",
    "Example: Environmental agencies use the Ash RGB to monitor ash dispersion over land and water after an eruption.",
    "Example: Emergency responders use the Ash RGB to support aviation and public-safety decisions during an eruptive crisis."
  ),
  convection: exampleSet(
    "Example: Agriculture support desks use the Convection RGB to flag rapidly growing storm cells before hail or intense rain reaches fields.",
    "Example: Aviation forecasters use the Convection RGB to track convective initiation and overshooting storm towers near busy terminals.",
    "Example: Water-resource managers use the Convection RGB to spot storms likely to produce intense runoff over catchments.",
    "Example: Disaster cells use the Convection RGB to identify the strongest thunderstorm cores during flash-flood or wind emergencies."
  ),
  fog: exampleSet(
    "Example: Farming communities use the Fog/Low Cloud RGB around sunrise to judge whether persistent low cloud may delay drying or harvest activity.",
    "Example: Airport forecasters use the Fog/Low Cloud RGB to separate fog and stratus from higher cloud around terminals.",
    "Example: Wetland and river-basin managers use the Fog/Low Cloud RGB to monitor low cloud trapped in valleys.",
    "Example: Emergency services use the Fog/Low Cloud RGB to assess visibility problems affecting road movement during an incident."
  ),
  night_fog: exampleSet(
    "Example: Growers use the Night Fog RGB before dawn to see whether fog is lingering over orchards and low-lying farmland.",
    "Example: Aviation meteorologists use the Night Fog RGB overnight to assess runway visibility hazards from fog or stratus.",
    "Example: Natural-resource teams use the Night Fog RGB to monitor nocturnal low cloud pooling in valleys and coastal zones.",
    "Example: Disaster managers use the Night Fog RGB when overnight visibility restrictions complicate evacuation or road response."
  ),
  day_microphysics: exampleSet(
    "Example: Agriculture forecasters use the Day Microphysics RGB to tell apart water cloud, ice cloud, and developing storms over crop regions.",
    "Example: Aviation desks use the Day Microphysics RGB to identify cloud phase and structure relevant to icing and convective hazards.",
    "Example: Snow and hydrology teams use the Day Microphysics RGB to distinguish cloud types over mountains and basins.",
    "Example: Emergency meteorologists use the Day Microphysics RGB to analyze storm cloud composition during a severe-weather event."
  ),
  night_microphysics: exampleSet(
    "Example: Agriculture teams use the Night Microphysics RGB overnight to see low cloud and fog that may affect early-morning field operations.",
    "Example: Aviation forecasters rely on the Night Microphysics RGB to monitor fog, stratus, and convective cloud phase at night.",
    "Example: Resource planners use the Night Microphysics RGB to follow low cloud decks over coastal waters and interior basins after dark.",
    "Example: Emergency centers use the Night Microphysics RGB during nighttime storms when visible imagery is unavailable."
  ),
  cloudtop: exampleSet(
    "Example: Agricultural advisors use Cloud Top products to spot the coldest, strongest storm towers approaching cultivated districts.",
    "Example: Aviation meteorologists use Cloud Top products to estimate the altitude and severity of cloud hazards near routes.",
    "Example: Natural-resource teams use Cloud Top imagery to compare deep convective growth over mountain watersheds.",
    "Example: Disaster responders use Cloud Top imagery to focus on storm cells most likely to produce intense rain or hail."
  ),
  ir_overview: exampleSet(
    "Example: Farm services use the IR Overview as an all-hours weather background when planning dawn operations under widespread cloud.",
    "Example: Aviation control centers use the IR Overview for a quick continuous scan of cloud systems affecting regional flying weather.",
    "Example: Environmental agencies use the IR Overview to monitor cloud cover over large landscapes through day and night.",
    "Example: Emergency teams use the IR Overview as a simple always-available situational map during storms and heavy rain."
  ),
  natural_with_night_fog: exampleSet(
    "Example: Agriculture advisors use Natural + Night Fog to transition from daytime land/cloud monitoring into overnight fog awareness without changing products.",
    "Example: Aviation forecasters use Natural + Night Fog to keep a familiar daytime-style view while still picking up nighttime fog near airports.",
    "Example: Natural-resource teams use Natural + Night Fog to maintain continuity in monitoring cloud and fog over valleys and reservoirs across sunset.",
    "Example: Emergency operations use Natural + Night Fog to brief day-to-night changes in cloud and low-visibility conditions during a prolonged event."
  ),
  fire_temperature_eumetsat: exampleSet(
    "Example: Agricultural authorities use Fire Temperature to detect crop-residue burning or wildfire hotspots near farming zones.",
    "Example: Aviation desks use Fire Temperature to note strong heat sources and associated smoke that may affect low-level visibility.",
    "Example: Forestry and land agencies use Fire Temperature to pinpoint active wildfire fronts for rapid assessment.",
    "Example: Emergency responders use Fire Temperature to prioritize fire-ground surveillance and resource deployment."
  ),
  low_cloud_night: exampleSet(
    "Example: Farmers use Low Cloud Night products to assess whether pre-dawn low cloud may delay evaporation and field access.",
    "Example: Aviation forecasters use Low Cloud Night products to focus specifically on stratus and fog around airports overnight.",
    "Example: Resource agencies use Low Cloud Night products to watch valley and coastal cloud accumulation after sunset.",
    "Example: Emergency services use Low Cloud Night products when nocturnal low visibility affects road, rescue, or helicopter operations."
  ),
};

const KEYWORD_GROUPS: Array<{
  match: (name: string) => boolean;
  examples: Record<DomainKey, string>;
}> = [
  {
    match: (name) => name.includes("microphysics"),
    examples: PRODUCT_EXAMPLES.night_microphysics,
  },
  {
    match: (name) => name.includes("convection") || name.includes("storm"),
    examples: PRODUCT_EXAMPLES.convection,
  },
  {
    match: (name) => name.includes("fog") || name.includes("low_cloud"),
    examples: PRODUCT_EXAMPLES.night_fog,
  },
  {
    match: (name) => name.includes("dust"),
    examples: PRODUCT_EXAMPLES.dust,
  },
  {
    match: (name) => name.includes("ash") || name.includes("so2"),
    examples: PRODUCT_EXAMPLES.ash,
  },
  {
    match: (name) => name.includes("airmass") || name.includes("tropopause") || name.includes("ozone") || name.includes("moisture_ridge") || name.includes("water_vapor") || name.includes("water_vapors") || name.includes("wv_"),
    examples: PRODUCT_EXAMPLES.airmass,
  },
  {
    match: (name) => name.includes("fire") || name.includes("rocket_plume"),
    examples: PRODUCT_EXAMPLES.fire_temperature_eumetsat,
  },
  {
    match: (name) => name.includes("cloudtop") || name.includes("cold_cloud_tops") || name.includes("overshooting_tops"),
    examples: PRODUCT_EXAMPLES.cloudtop,
  },
  {
    match: (name) => name.includes("ir_overview") || name.includes("night_ir_alpha") || name.includes("ir108_3d") || name.includes("split_window") || name.includes("thermal_triplet") || name.includes("ir_window_sandwich"),
    examples: PRODUCT_EXAMPLES.ir_overview,
  },
  {
    match: (name) => name.includes("natural") || name.includes("overview"),
    examples: PRODUCT_EXAMPLES.natural_color,
  },
];

export function productDomainExample(
  productName: string,
  domain: DomainKey
): string {
  const exact = PRODUCT_EXAMPLES[productName];
  if (exact) return exact[domain];

  const normalized = productName.toLowerCase();
  const keywordMatch = KEYWORD_GROUPS.find((group) => group.match(normalized));
  if (keywordMatch) return keywordMatch.examples[domain];

  return DEFAULT_EXAMPLES[domain];
}
