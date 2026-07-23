"use client";

import {
  BoundingSphere,
  Cartesian3,
  Color,
  Ellipsoid,
  HeadingPitchRange,
  ImageryLayer,
  Ion,
  IonWorldImageryStyle,
  Matrix4,
  Rectangle,
  SceneMode,
  SingleTileImageryProvider,
  Viewer,
  createWorldImageryAsync,
} from "cesium";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

const MIN_CAMERA_ALTITUDE = 250_000;
const MAX_CAMERA_ALTITUDE = 35_000_000;
const EARTH_RADIUS = Ellipsoid.WGS84.maximumRadius;

export type CesiumGlobeOverlayDescriptor = {
  id: string;
  imageUrl: string;
  west: number;
  south: number;
  east: number;
  north: number;
  visible: boolean;
  active: boolean;
};

export type CesiumGlobeCanvasProps = {
  overlays: readonly CesiumGlobeOverlayDescriptor[];
  className?: string;
  style?: CSSProperties;
  ariaLabel?: string;
  ionToken?: string;
  onSetupRequired?: (message: string) => void;
  onError?: (error: Error) => void;
};

type SetupState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "missing-token"; message: string }
  | { kind: "error"; message: string };

type OverlayLayer = {
  signature: string;
  layer: ImageryLayer;
};

function asError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

function overlaySignature(overlay: CesiumGlobeOverlayDescriptor): string {
  return [
    overlay.imageUrl,
    overlay.west,
    overlay.south,
    overlay.east,
    overlay.north,
  ].join("\u0000");
}

/**
 * Direct CesiumJS globe surface. It owns the Viewer and imagery-layer
 * lifecycles; higher-level controls should only update overlay descriptors.
 */
export function CesiumGlobeCanvas({
  overlays,
  className,
  style,
  ariaLabel = "Interactive 3D Earth",
  ionToken = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN,
  onSetupRequired,
  onError,
}: CesiumGlobeCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const overlayLayersRef = useRef(new Map<string, OverlayLayer>());
  const setupCallbackRef = useRef(onSetupRequired);
  const errorCallbackRef = useRef(onError);
  const [viewerRevision, setViewerRevision] = useState(0);
  const [setupState, setSetupState] = useState<SetupState>({ kind: "loading" });

  setupCallbackRef.current = onSetupRequired;
  errorCallbackRef.current = onError;

  const normalizedToken = ionToken?.trim() ?? "";

  useEffect(() => {
    const container = containerRef.current;
    const overlayLayers = overlayLayersRef.current;
    if (!container) {
      return;
    }

    if (!normalizedToken) {
      const message =
        "Cesium ion is not configured. Set NEXT_PUBLIC_CESIUM_ION_TOKEN to load Cesium World Imagery.";
      setSetupState({ kind: "missing-token", message });
      setupCallbackRef.current?.(message);
      return;
    }

    let cancelled = false;
    let viewer: Viewer | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let removeMoveEndListener: (() => void) | null = null;

    const fitEarth = (targetViewer: Viewer) => {
      targetViewer.camera.viewBoundingSphere(
        new BoundingSphere(Cartesian3.ZERO, EARTH_RADIUS),
        new HeadingPitchRange(0, -Math.PI / 2, EARTH_RADIUS * 2.25),
      );
      targetViewer.camera.lookAtTransform(Matrix4.IDENTITY);
      targetViewer.scene.requestRender();
    };

    const enforceCameraConstraints = (targetViewer: Viewer) => {
      const camera = targetViewer.camera;
      const cartographic = camera.positionCartographic;
      const clampedAltitude = Math.min(
        MAX_CAMERA_ALTITUDE,
        Math.max(MIN_CAMERA_ALTITUDE, cartographic.height),
      );

      if (clampedAltitude !== cartographic.height) {
        camera.setView({
          destination: Cartesian3.fromRadians(
            cartographic.longitude,
            cartographic.latitude,
            clampedAltitude,
          ),
          orientation: {
            heading: camera.heading,
            pitch: camera.pitch,
            roll: camera.roll,
          },
        });
      }

    };

    const initialize = async () => {
      setSetupState({ kind: "loading" });
      Ion.defaultAccessToken = normalizedToken;

      try {
        viewer = new Viewer(container, {
          baseLayer: false,
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          navigationHelpButton: false,
          sceneMode: SceneMode.SCENE3D,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          vrButton: false,
          requestRenderMode: true,
        });

        const controller = viewer.scene.screenSpaceCameraController;
        controller.enableInputs = true;
        controller.enableRotate = true;
        controller.enableZoom = true;
        controller.enableTilt = true;
        controller.enableTranslate = false;
        controller.enableLook = false;
        controller.minimumZoomDistance = MIN_CAMERA_ALTITUDE;
        controller.maximumZoomDistance = MAX_CAMERA_ALTITUDE;

        viewer.scene.globe.baseColor = Color.fromCssColorString("#061820");
        fitEarth(viewer);

        const worldImagery = await createWorldImageryAsync({
          style: IonWorldImageryStyle.AERIAL_WITH_LABELS,
        });
        if (cancelled || !viewer || viewer.isDestroyed()) {
          return;
        }

        viewer.imageryLayers.addImageryProvider(worldImagery, 0);

        const activeViewer = viewer;
        removeMoveEndListener = activeViewer.camera.moveEnd.addEventListener(
          () => enforceCameraConstraints(activeViewer),
        );
        resizeObserver = new ResizeObserver(() => {
          if (activeViewer.isDestroyed()) {
            return;
          }
          activeViewer.resize();
          activeViewer.scene.requestRender();
        });
        resizeObserver.observe(container);

        viewerRef.current = viewer;
        setViewerRevision((revision) => revision + 1);
        setSetupState({ kind: "ready" });
      } catch (value) {
        const error = asError(value);
        if (!cancelled) {
          setSetupState({ kind: "error", message: error.message });
          errorCallbackRef.current?.(error);
        }
        if (viewer && !viewer.isDestroyed()) {
          viewer.destroy();
          viewer = null;
        }
      }
    };

    void initialize();

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      removeMoveEndListener?.();
      viewerRef.current = null;
      overlayLayers.clear();
      if (viewer && !viewer.isDestroyed()) {
        viewer.destroy();
      }
    };
  }, [normalizedToken]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) {
      return;
    }

    let cancelled = false;
    const imageryLayers = viewer.imageryLayers;
    const layerEntries = overlayLayersRef.current;
    const desiredIds = new Set(overlays.map(({ id }) => id));

    for (const [id, entry] of layerEntries) {
      if (!desiredIds.has(id)) {
        imageryLayers.remove(entry.layer, true);
        layerEntries.delete(id);
      }
    }

    const synchronize = async () => {
      try {
        for (const overlay of overlays) {
          if (cancelled || viewer.isDestroyed()) {
            return;
          }

          const signature = overlaySignature(overlay);
          let entry = layerEntries.get(overlay.id);
          if (entry && entry.signature !== signature) {
            imageryLayers.remove(entry.layer, true);
            layerEntries.delete(overlay.id);
            entry = undefined;
          }

          if (!entry) {
            const provider = await SingleTileImageryProvider.fromUrl(
              overlay.imageUrl,
              {
                rectangle: Rectangle.fromDegrees(
                  overlay.west,
                  overlay.south,
                  overlay.east,
                  overlay.north,
                ),
              },
            );
            if (cancelled || viewer.isDestroyed()) {
              return;
            }
            entry = {
              signature,
              layer: imageryLayers.addImageryProvider(provider),
            };
            layerEntries.set(overlay.id, entry);
          }

          entry.layer.show = overlay.visible;
          entry.layer.alpha = overlay.active ? 1 : 0.72;
        }

        for (const overlay of overlays) {
          const entry = layerEntries.get(overlay.id);
          if (entry) {
            imageryLayers.raiseToTop(entry.layer);
          }
        }
        for (const overlay of overlays) {
          if (overlay.active) {
            const entry = layerEntries.get(overlay.id);
            if (entry) {
              imageryLayers.raiseToTop(entry.layer);
            }
          }
        }
        viewer.scene.requestRender();
      } catch (value) {
        if (!cancelled) {
          errorCallbackRef.current?.(asError(value));
        }
      }
    };

    void synchronize();
    return () => {
      cancelled = true;
    };
  }, [overlays, viewerRevision]);

  const statusMessage =
    setupState.kind === "missing-token" || setupState.kind === "error"
      ? setupState.message
      : null;

  return (
    <div
      className={className}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        minHeight: 320,
        overflow: "hidden",
        background: "#061820",
        ...style,
      }}
      aria-label={ariaLabel}
    >
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      {statusMessage ? (
        <div
          role={setupState.kind === "error" ? "alert" : "status"}
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 1,
            display: "grid",
            placeItems: "center",
            padding: 24,
            color: "#e8f1f4",
            background: "#061820",
            textAlign: "center",
          }}
        >
          {statusMessage}
        </div>
      ) : null}
    </div>
  );
}
