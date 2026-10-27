"use client";

import Dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { BaseNode, BaseNodeContent, BaseNodeHeader, BaseNodeHeaderTitle } from "@/components/base-node";
import type { TopologyEdge, TopologyNode } from "@/types/contracts";

// Audit topology for the bank-transfer sample app, auto-laid-out with dagre.
// Shapes follow the AuditResult contract (TopologyNode / TopologyEdge, PLAN §7.4).

export type TopoNode = TopologyNode;
export type TopoEdge = TopologyEdge;

/** flag: what the audit found in this node, e.g. "race condition" */
// A mapped copy of the contract interface, so React Flow's Record<string, unknown> data constraint holds.
type ServiceData = { [K in keyof TopoNode]: TopoNode[K] } & { flag?: string; pulse?: boolean };

const KIND_LABEL: Record<TopoNode["kind"], string> = {
  route: "Route",
  service: "Service",
  store: "Store",
  external: "External",
  worker: "Worker",
};

function ServiceNode({ data }: NodeProps<Node<ServiceData>>) {
  return (
    <BaseNode className={`topo-node ${data.flagged ? "is-flagged" : ""} ${data.pulse ? "is-pulsing" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <BaseNodeHeader>
        <BaseNodeHeaderTitle className="topo-title">{data.label}</BaseNodeHeaderTitle>
        <span className="topo-kind">{KIND_LABEL[data.kind]}</span>
      </BaseNodeHeader>
      <BaseNodeContent className="topo-body">
        {data.file && (
          <code className="topo-file" translate="no">
            {data.file}
          </code>
        )}
        {data.flagged && <span className="topo-flag">Flagged{data.flag ? `: ${data.flag}` : ""}</span>}
      </BaseNodeContent>
      <Handle type="source" position={Position.Right} />
    </BaseNode>
  );
}

const nodeTypes = { service: ServiceNode };
const NODE_W = 230;
const NODE_H = 92;

function layout(nodes: TopoNode[], edges: TopoEdge[], flags: Record<string, string>) {
  const g = new Dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 70 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  Dagre.layout(g);
  return nodes.map<Node<ServiceData>>((n) => {
    const p = g.node(n.id);
    return { id: n.id, type: "service", position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 }, data: { ...n, flag: flags[n.id] } };
  });
}

export function TopologyView({
  nodes,
  edges,
  selectedId,
  onSelect,
  flags = {},
  pulseId = null,
}: {
  nodes: TopoNode[];
  edges: TopoEdge[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** node id → what the audit flagged there */
  flags?: Record<string, string>;
  /** the node SAM matched to the candidate's circle (defense.sam.highlight) pulses */
  pulseId?: string | null;
}) {
  const flowNodes = useMemo(
    () =>
      layout(nodes, edges, flags).map((n) => ({
        ...n,
        selected: n.id === selectedId,
        data: { ...n.data, pulse: n.id === pulseId },
      })),
    [nodes, edges, flags, selectedId, pulseId],
  );
  // Edges stay still; flagged paths are red, everything else quiet grey.
  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => {
        const hot = nodes.find((n) => n.id === e.target)?.flagged || nodes.find((n) => n.id === e.source)?.flagged;
        return {
          id: `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          label: e.label ?? undefined,
          style: { stroke: hot ? "#ffffff" : "#3a3a40", strokeWidth: hot ? 2 : 1.5 },
          labelStyle: { fill: "#a2a2a8", fontSize: 12 },
          labelBgStyle: { fill: "#0c0c0d" },
        };
      }),
    [nodes, edges],
  );

  return (
    <div className="topo" aria-label="Project topology diagram">
      <ReactFlow
        colorMode="dark"
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_, n) => onSelect?.(n.id)}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background gap={24} size={1} color="#1e1e22" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
