import { useEffect } from "react";
import { CircleMarker, MapContainer, Polygon, Polyline, TileLayer, Tooltip, ZoomControl, useMap } from "react-leaflet";
import type { LatLngBoundsExpression, LatLngExpression, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import type { BusinessNode, ShockState, SupplyEdge } from "../types";

interface MapViewProps {
  nodes: BusinessNode[];
  edges: SupplyEdge[];
  selectedId: string;
  shock: ShockState;
  onSelect: (id: string) => void;
}

const southernVietnamBounds: LatLngBoundsExpression = [[8.35, 104.45], [12.35, 109.15]];

const binhDuongBoundary: LatLngExpression[] = [
  [10.82, 106.56],
  [10.88, 106.49],
  [11.11, 106.42],
  [11.50, 106.48],
  [11.46, 106.80],
  [11.27, 106.94],
  [11.04, 106.91],
  [10.87, 106.81]
];

const southernFocusBoundary: LatLngExpression[] = [
  [8.42, 104.58], [8.58, 105.08], [9.06, 105.37], [9.44, 106.02],
  [10.03, 106.78], [10.34, 107.12], [10.72, 107.23], [10.95, 107.62],
  [11.19, 108.63], [11.87, 108.93], [12.21, 108.56], [11.83, 107.63],
  [11.56, 106.49], [11.01, 105.58], [10.56, 104.90], [9.72, 104.52]
];

const roleStroke: Record<BusinessNode["type"], string> = {
  manufacturer: "#2dd4bf",
  distributor: "#38bdf8",
  wholesaler: "#a78bfa",
  retailer: "#f8fafc",
  logistics_partner: "#fbbf24",
  financial_partner: "#c084fc"
};

function riskColor(node: BusinessNode, shock: ShockState) {
  if (shock.active && node.id === shock.shockNodeId) return "#ef4444";
  if (shock.active && shock.affectedNodeIds.includes(node.id)) return "#f59e0b";
  if (node.risk >= 70) return "#ef4444";
  if (node.risk >= 45) return "#f59e0b";
  return "#84cc16";
}

function radiusFor(node: BusinessNode, selected: boolean) {
  const base = node.type === "manufacturer" ? 10 : node.type === "distributor" ? 8 : node.type === "financial_partner" ? 7 : 6;
  return base + (selected ? 3 : 0);
}

function FitNetwork({ nodes }: { nodes: BusinessNode[] }) {
  const map = useMap();
  useEffect(() => {
    if (!nodes.length) return;
    if (nodes.length >= 20) {
      map.fitBounds(southernVietnamBounds, { padding: [22, 22] });
      return;
    }
    const bounds: LatLngBoundsExpression = nodes.map((node) => [node.lat, node.lng] as [number, number]);
    map.fitBounds(bounds, { padding: [54, 54], maxZoom: 9 });
  }, [map, nodes]);
  return null;
}

export function MapView({ nodes, edges, selectedId, shock, onSelect }: MapViewProps) {
  const byId = new Map(nodes.map((node) => [node.id, node]));

  return (
    <div className="leaflet-shell" data-testid="southern-map">
      <MapContainer
        center={[10.75, 106.85]}
        zoom={7}
        minZoom={6}
        maxZoom={13}
        maxBounds={[[7.8, 103.8], [13.1, 110]]}
        scrollWheelZoom
        zoomControl={false}
        className="leaflet-map"
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors &copy; CARTO'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        <ZoomControl position="bottomleft" />
        <FitNetwork nodes={nodes} />

        <Polygon positions={southernFocusBoundary} pathOptions={{ color: "#0ea5e9", weight: 1, opacity: 0.28, fillColor: "#082f49", fillOpacity: 0.08 }} />
        <Polygon positions={binhDuongBoundary} pathOptions={{ color: "#22d3ee", weight: 9, opacity: 0.12, fillOpacity: 0 }} />
        <Polygon positions={binhDuongBoundary} pathOptions={{ color: "#67e8f9", weight: 2, opacity: 0.92, fillColor: "#0e7490", fillOpacity: 0.13 }}>
          <Tooltip sticky>Binh Duong focus area</Tooltip>
        </Polygon>

        {edges.map((edge) => {
          const source = byId.get(edge.sourceId);
          const target = byId.get(edge.targetId);
          if (!source || !target) return null;
          const impacted = shock.active && shock.affectedEdgeIds.includes(edge.id);
          const support = edge.relationType && edge.relationType !== "supply";
          const pathOptions: PathOptions = {
            color: impacted ? "#fb7185" : support ? "#c084fc" : "#22d3ee",
            weight: impacted ? 3 : support ? 1.8 : 1.25,
            opacity: impacted ? 0.9 : support ? 0.72 : 0.46,
            dashArray: impacted ? "7 7" : support ? "3 5" : undefined
          };
          return (
            <Polyline key={edge.id} positions={[[source.lat, source.lng], [target.lat, target.lng]]} pathOptions={pathOptions}>
              <Tooltip sticky>
                <strong>{source.name} to {target.name}</strong><br />
                {edge.relationType ?? "supply"} · {edge.category} · {edge.leadTimeDays}d lead time
              </Tooltip>
            </Polyline>
          );
        })}

        {nodes.map((node) => {
          const selected = node.id === selectedId;
          return (
            <CircleMarker
              key={node.id}
              center={[node.lat, node.lng]}
              radius={radiusFor(node, selected)}
              pathOptions={{
                color: selected ? "#ffffff" : roleStroke[node.type] ?? "#ffffff",
                fillColor: riskColor(node, shock),
                fillOpacity: 0.95,
                opacity: 1,
                weight: selected ? 4 : 2
              }}
              eventHandlers={{ click: () => onSelect(node.id) }}
            >
              <Tooltip direction="top" offset={[0, -8]} opacity={1}>
                <strong>{node.name}</strong><br />
                {node.type.replace("_", " ")} · {node.province}<br />
                Risk {node.risk}/100 · Health {node.health}/100
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <div className="map-overlay-label">
        <span>Southern Vietnam</span>
        <strong>Binh Duong highlighted</strong>
      </div>
    </div>
  );
}
