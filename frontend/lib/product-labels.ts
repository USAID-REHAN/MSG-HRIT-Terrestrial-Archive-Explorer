/** Canonical SEVIRI product order and display labels. */

export const CHANNEL_ORDER = [
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
] as const;

/** Keep in sync with backend `app.processing.composite_catalog.COMPOSITE_NAMES`. */
export const COMPOSITE_ORDER = [
  "natural_color",
  "natural_color_nocorr",
  "natural_color_raw",
  "natural_enh",
  "overview",
  "overview_raw",
  "airmass",
  "dust",
  "ash",
  "convection",
  "fog",
  "night_fog",
  "day_microphysics",
  "day_microphysics_winter",
  "night_microphysics",
  "night_microphysics_tropical",
  "24h_microphysics",
  "day_severe_storms",
  "day_severe_storms_tropical",
  "snow",
  "green_snow",
  "cloudtop",
  "cloudtop_daytime",
  "colorized_ir_clouds",
  "ir_overview",
  "ir_cloud_day",
  "ir108_3d",
  "overshooting_tops",
  "natural_with_night_fog",
  "natural_color_raw_with_night_ir",
  "night_ir_alpha",
  "rocket_plume_night",
  "water_vapors1",
  "water_vapors2",
  "fire_temperature_eumetsat",
  "cloud_convective_storms",
  "dust_cloud",
  "ir_window_sandwich",
  "airmass_jet",
  "night_microphysics_simple",
  "wv_diff_rgb",
  "split_window_rgb",
  "ozone_airmass",
  "thermal_triplet",
  "moisture_ridge",
  "tropopause_fold",
  "cold_cloud_tops",
  "night_convection",
  "so2_proxy",
  "low_cloud_night",
] as const;

const LABELS: Record<string, string> = {
  HRV: "HRV",
  VIS006: "VIS 0.6",
  VIS008: "VIS 0.8",
  IR_016: "IR 1.6",
  IR_039: "IR 3.9",
  WV_062: "WV 6.2",
  WV_073: "WV 7.3",
  IR_087: "IR 8.7",
  IR_097: "IR 9.7",
  IR_108: "IR 10.8",
  IR_120: "IR 12.0",
  IR_134: "IR 13.4",
  natural_color: "Natural Colour",
  natural_color_nocorr: "Natural Colour (no corr.)",
  natural_color_raw: "Natural Colour (raw)",
  natural_enh: "Natural Colour Enhanced",
  overview: "Overview",
  overview_raw: "Overview (raw)",
  airmass: "Air Mass",
  dust: "Dust",
  ash: "Ash",
  convection: "Convection",
  fog: "Fog / Low Cloud",
  night_fog: "Night Fog",
  day_microphysics: "Day Microphysics",
  day_microphysics_winter: "Day Microphysics (winter)",
  night_microphysics: "Night Microphysics",
  night_microphysics_tropical: "Night Microphysics (tropical)",
  "24h_microphysics": "24h Microphysics",
  day_severe_storms: "Day Severe Storms",
  day_severe_storms_tropical: "Day Severe Storms (tropical)",
  snow: "Snow",
  green_snow: "Green Snow",
  cloudtop: "Cloud Top",
  cloudtop_daytime: "Cloud Top (daytime)",
  colorized_ir_clouds: "Colorized IR Clouds",
  ir_overview: "IR Overview",
  ir_cloud_day: "IR Cloud Day",
  ir108_3d: "IR 10.8 3D",
  overshooting_tops: "Overshooting Tops",
  natural_with_night_fog: "Natural + Night Fog",
  natural_color_raw_with_night_ir: "Natural Raw + Night IR",
  night_ir_alpha: "Night IR (alpha)",
  rocket_plume_night: "Rocket Plume (night)",
  water_vapors1: "Water Vapour RGB 1",
  water_vapors2: "Water Vapour RGB 2",
  fire_temperature_eumetsat: "Fire Temperature (EUMETSAT)",
  cloud_convective_storms: "Convective Storms RGB",
  dust_cloud: "Dust / Cloud RGB",
  ir_window_sandwich: "IR Window Sandwich",
  airmass_jet: "Air Mass / Jet RGB",
  night_microphysics_simple: "Night Microphysics (simple)",
  wv_diff_rgb: "Water Vapour Difference RGB",
  split_window_rgb: "Split-Window RGB",
  ozone_airmass: "Ozone / Air Mass RGB",
  thermal_triplet: "Thermal Triplet RGB",
  moisture_ridge: "Moisture Ridge RGB",
  tropopause_fold: "Tropopause Fold RGB",
  cold_cloud_tops: "Cold Cloud Tops RGB",
  night_convection: "Night Convection RGB",
  so2_proxy: "SO₂ Proxy RGB",
  low_cloud_night: "Low Cloud Night RGB",
  final_globe_mix: "Final Globe Mix",
};

export function productLabel(name: string): string {
  return LABELS[name] || name.replaceAll("_", " ");
}

export function productShortLabel(name: string): string {
  return name;
}

export function sortProductsByKind<T extends { product_name: string; product_kind: string }>(
  products: T[]
): T[] {
  const channelRank = new Map<string, number>(
    CHANNEL_ORDER.map((n, i) => [n, i])
  );
  const compositeRank = new Map<string, number>(
    COMPOSITE_ORDER.map((n, i) => [n, i])
  );

  return [...products].sort((a, b) => {
    if (a.product_kind !== b.product_kind) {
      return a.product_kind === "channel" ? -1 : 1;
    }
    const rank =
      a.product_kind === "channel"
        ? (channelRank.get(a.product_name) ?? 999) -
          (channelRank.get(b.product_name) ?? 999)
        : (compositeRank.get(a.product_name) ?? 999) -
          (compositeRank.get(b.product_name) ?? 999);
    return rank || a.product_name.localeCompare(b.product_name);
  });
}
