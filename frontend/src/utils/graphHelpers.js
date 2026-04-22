import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force';
import { DEPTH_RADIUS, ROOT_R, FOLDER_W, NODE_W, FOLDER_H, NODE_H, LINK_DIST, REPULSION, COLLISION_R, SIM_TICKS } from '../constants/flowConstants';

export function buildTree(paths) {
    const root = { id: 'root', name: '/', type: 'folder', children: {}, path: '' };
    paths.forEach(path => {
        const parts = path.split('/');
        let current = root;
        let currentPath = '';
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            const isFile = i === parts.length - 1;
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            if (!current.children[part]) {
                current.children[part] = {
                    id: currentPath, name: part,
                    type: isFile ? 'file' : 'folder',
                    children: {}, path: currentPath,
                };
            }
            current = current.children[part];
        }
    });
    return root;
}

export function generateGraph(tree, expandedFolders) {
    const nodes = [];
    const edges = [];

    // Root node fixed at center
    nodes.push({
        id: '__root__',
        type: 'rootNode',
        data: { label: tree.name || '/' },
        position: { x: 0, y: 0 },
    });

    function walk(node, parentId, depth, angleStart, angleSpan) {
        const children = Object.values(node.children).sort((a, b) => {
            if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
            return a.name.localeCompare(b.name);
        });
        const total = children.length;

        children.forEach((child, idx) => {
            const isFolder = child.type === 'folder';
            const isExpanded = expandedFolders.has(child.id);

            const span = angleSpan ?? (2 * Math.PI);
            const theta = (angleStart ?? 0) + (total > 1 ? (span / total) * idx : 0);
            const r = depth * DEPTH_RADIUS;

            nodes.push({
                id: child.id,
                type: isFolder ? 'folderNode' : 'fileNode',
                data: {
                    label: child.name,
                    isExpanded,
                    hasChildren: Object.keys(child.children).length > 0,
                    nodeId: child.id,
                },
                position: { x: r * Math.cos(theta), y: r * Math.sin(theta) },
            });

            edges.push({
                id: `e-${parentId}-${child.id}`,
                source: parentId,
                target: child.id,
                type: 'floralEdge',
                style: { stroke: '#333', strokeWidth: 1 },
            });

            if (isFolder && isExpanded) {
                const childSpan = Math.min(span / Math.max(total, 1), Math.PI * 1.2);
                walk(child, child.id, depth + 1, theta - childSpan / 2, childSpan);
            }
        });
    }

    walk(tree, '__root__', 1, 0, 2 * Math.PI);
    return { nodes, edges };
}

export function applyForceLayout(nodes, edges) {
    const simNodes = nodes.map(n => ({
        id: n.id,
        x: n.position.x,
        y: n.position.y,
        fx: n.id === '__root__' ? 0 : null,
        fy: n.id === '__root__' ? 0 : null,
    }));

    const simEdges = edges.map(e => ({ source: e.source, target: e.target }));

    const sim = forceSimulation(simNodes)
        .force('link', forceLink(simEdges).id(d => d.id).distance(LINK_DIST).strength(0.7))
        .force('charge', forceManyBody().strength(REPULSION))
        .force('center', forceCenter(0, 0).strength(0.05))
        .force('collide', forceCollide(COLLISION_R).strength(0.8))
        .stop();

    sim.tick(SIM_TICKS);

    const posMap = {};
    simNodes.forEach(sn => { posMap[sn.id] = { x: sn.x, y: sn.y }; });

    return nodes.map(n => {
        const pos = posMap[n.id] || { x: 0, y: 0 };
        const w = n.type === 'rootNode' ? ROOT_R * 2 : n.type === 'folderNode' ? FOLDER_W : NODE_W;
        const h = n.type === 'rootNode' ? ROOT_R * 2 : n.type === 'folderNode' ? FOLDER_H : NODE_H;
        return { ...n, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
    });
}