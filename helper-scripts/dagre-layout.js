// Thin wrapper around @dagrejs/dagre for use by relayout-nodered-flows.py.
// Reads a graph from stdin, runs dagre layout, writes positions to stdout.
//
// Input:  {"settings": {rankdir, marginx, ...}, "nodes": [{id, width, height}], "edges": [{source, target}]}
// Output: {"width": N, "height": N, "nodes": {"id": {x, y}, ...}}

const dagre = require("@dagrejs/dagre");
const chunks = [];
process.stdin.on("data", (c) => chunks.push(c));
process.stdin.on("end", () => {
  const { settings, nodes, edges } = JSON.parse(Buffer.concat(chunks));
  const g = new dagre.graphlib.Graph();
  g.setGraph(settings);
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: n.width, height: n.height });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  const graph = g.graph();
  const out = { width: graph.width, height: graph.height, nodes: {} };
  for (const n of nodes) out.nodes[n.id] = g.node(n.id);
  process.stdout.write(JSON.stringify(out));
});
