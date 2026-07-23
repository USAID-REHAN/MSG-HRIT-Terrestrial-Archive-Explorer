"use client";

import { useEffect } from "react";
import {
  ImageOverlay,
  MapContainer,
  Rectangle,
  TileLayer,
  useMap,
} from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { useTheme } from "@/components/ThemeProvider";
import "leaflet/dist/leaflet.css";

export type MapLayerOverlay = {
  id: number;
  url: string;
  opacity: number;
  zIndex: number;
};

type Props = {
  center: [number, number];
  zoom: number;
  bounds: LatLngBoundsExpression;
  layers: MapLayerOverlay[];
  showBasemap?: boolean;
  className?: string;
};

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [16, 16], animate: false });
  }, [map, bounds]);
  return null;
}

/**
 * Web Mercator map canvas (Leaflet / EPSG:3857) — EUMETView-style stack of
 * transparent ImageOverlays over a basemap, focused on the Pakistan ROI.
 */
export function MercatorMapCanvas({
  center,
  zoom,
  bounds,
  layers,
  showBasemap = true,
  className = "",
}: Props) {
  const { theme } = useTheme();
  const tileUrl =
    theme === "light"
      ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className={className}
      scrollWheelZoom
      style={{ height: "100%", width: "100%", background: "var(--map-ocean-deep)" }}
    >
      {showBasemap ? (
        <TileLayer
          key={theme}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
          url={tileUrl}
          maxZoom={12}
        />
      ) : null}
      <FitBounds bounds={bounds} />
      <Rectangle
        bounds={bounds}
        pathOptions={{
          color: theme === "light" ? "#0d9488" : "#2dd4bf",
          weight: 1.5,
          dashArray: "6 4",
          fill: false,
          opacity: 0.85,
        }}
      />
      {layers.map((layer) => (
        <ImageOverlay
          key={layer.id}
          url={layer.url}
          bounds={bounds}
          opacity={layer.opacity}
          zIndex={layer.zIndex}
        />
      ))}
    </MapContainer>
  );
}
