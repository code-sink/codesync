import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    useReactFlow,
    ReactFlowProvider,
    Handle,
    Position,
    Panel,
    getBezierPath,
    BaseEdge,
} from 'reactflow';
import {
    forceSimulation,
    forceLink,
    forceManyBody,
    forceCenter,
    forceCollide,
} from 'd3-force';
import 'reactflow/dist/style.css';
import { getRepoDetails, getBranchHealth } from '../api';

// ─── Constants ───────────────────────────────────────────────────────────────

const NODE_W = 160;
const NODE_H = 36;
const FOLDER_W = 164;
const FOLDER_H = 40;
const ROOT_R = 32;

const DEPTH_RADIUS = 280;
const REPULSION    = -600;
const LINK_DIST    = 220;
const COLLISION_R  = 100;
const SIM_TICKS    = 300;

// ─── Icons ────────────────────────────────────────────────────────────────────

const FolderIcon = ({ open }) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
        {!open && <><line x1="12" y1="11" x2="12" y2="17" /><line x1="9" y1="14" x2="15" y2="14" /></>}
    </svg>
);

const getFileColor = (name) => {
    const ext = name.split('.').pop()?.toLowerCase();
    const colors = {
        js: '#f7df1e', jsx: '#61dafb', ts: '#3178c6', tsx: '#61dafb',
        css: '#2965f1', scss: '#c6538c', html: '#e34c26', json: '#5ba344',
        md: '#aaaaaa', py: '#3572A5', rb: '#701516', go: '#00ADD8',
        rs: '#dea584', java: '#b07219', cpp: '#f34b7d', c: '#555555',
        sh: '#89e051', yml: '#cb171e', yaml: '#cb171e', env: '#4aad4a',
        png: '#a855f7', jpg: '#a855f7', svg: '#ff9900', gif: '#a855f7',
        lock: '#888888',
    };
    return colors[ext] || '#666';
};

const getFileIcon = (name) => {
    const color = getFileColor(name);
    return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" />
            <polyline points="13 2 13 9 20 9" />
        </svg>
    );
};

// ─── Tree Building ────────────────────────────────────────────────────────────

function buildTree(paths) {
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

// ─── Graph Generation ─────────────────────────────────────────────────────────

function generateGraph(tree, expandedFolders) {
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

// ─── D3 Force Layout ──────────────────────────────────────────────────────────

function applyForceLayout(nodes, edges) {
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

// ─── Custom Edge: Floral Bezier ───────────────────────────────────────────────

const FloralEdge = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style }) => {
    const [edgePath] = getBezierPath({
        sourceX, sourceY, sourcePosition,
        targetX, targetY, targetPosition,
        curvature: 0.3,
    });
    return <BaseEdge id={id} path={edgePath} style={{ ...style, strokeOpacity: 0.6 }} />;
};

// ─── Custom Node: Root ────────────────────────────────────────────────────────

const RootNode = ({ data, selected }) => (
    <div style={{
        width: ROOT_R * 2, height: ROOT_R * 2,
        borderRadius: '50%',
        background: selected ? '#1a1a1a' : '#111111',
        border: `1.5px solid ${selected ? '#ffffff' : '#444444'}`,
        boxShadow: selected ? '0 0 0 1px #555' : 'none',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'default', position: 'relative',
    }}>
        <Handle type="source" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#ededed">
            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
        </svg>
    </div>
);

// ─── Custom Node: Folder ──────────────────────────────────────────────────────

const FolderNode = ({ data, selected }) => (
    <div
        style={{
            width: FOLDER_W, height: FOLDER_H,
            background: selected ? '#1a1a1a' : '#111111',
            border: `1px solid ${selected ? '#555555' : '#2a2a2a'}`,
            borderRadius: 10,
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 12px', cursor: 'pointer',
            boxShadow: selected
                ? '0 0 0 1px #444'
                : '0 2px 8px rgba(0,0,0,0.5)',
            transition: 'all 0.18s ease',
            fontFamily: '"Geist Mono", "JetBrains Mono", monospace',
            position: 'relative',
        }}
        onClick={() => data.onToggle?.(data.nodeId)}
    >
        <Handle type="target" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="target" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="target" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="target" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />
        <Handle type="source" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
        <div style={{ color: data.isExpanded ? '#ededed' : '#888888', flexShrink: 0 }}>
            <FolderIcon open={data.isExpanded} />
        </div>
        <span style={{
            fontSize: 11, color: '#ededed', fontWeight: 500,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            flex: 1, letterSpacing: '0.01em',
        }}>
            {data.label}
        </span>
        {data.hasChildren && (
            <span style={{ fontSize: 9, color: data.isExpanded ? '#888' : '#555', flexShrink: 0 }}>
                {data.isExpanded ? '▾' : '▸'}
            </span>
        )}
    </div>
);

// ─── Custom Node: File ────────────────────────────────────────────────────────

const FileNode = ({ data, selected }) => {
    const ext = data.label.split('.').pop()?.toLowerCase();
    const accentColor = getFileColor(data.label);
    return (
        <div style={{
            width: NODE_W, height: NODE_H,
            background: selected ? '#0e0e0e' : '#070707',
            border: `1px solid ${selected ? '#333333' : '#1a1a1a'}`,
            borderLeft: `2px solid ${accentColor}44`,
            borderRadius: 7,
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '0 10px', cursor: 'default',
            boxShadow: 'none',
            transition: 'all 0.15s ease',
            fontFamily: '"Geist Mono", "JetBrains Mono", monospace',
            position: 'relative',
        }}>
            <Handle type="target" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
            <Handle type="target" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
            <Handle type="target" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />
            <Handle type="target" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
            <div style={{ flexShrink: 0 }}>{getFileIcon(data.label)}</div>
            <span style={{
                fontSize: 11, color: '#ededed', fontWeight: 500,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                flex: 1, letterSpacing: '0.01em',
            }}>
                {data.label}
            </span>
            {ext && (
                <span style={{
                    fontSize: 9, color: accentColor + '99',
                    background: accentColor + '11',
                    border: `1px solid ${accentColor}22`,
                    borderRadius: 3, padding: '1px 4px',
                    flexShrink: 0, letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                }}>
                    {ext}
                </span>
            )}
        </div>
    );
};

// ─── Registries ───────────────────────────────────────────────────────────────

const nodeTypes = { rootNode: RootNode, folderNode: FolderNode, fileNode: FileNode };
const edgeTypes = { floralEdge: FloralEdge };

// ─── Branch Health Bar ─────────────────────────────────────────────────────

const BranchHealthBar = ({ health, loading }) => {
    const [open, setOpen] = useState(false);
    const [expandedFile, setExpandedFile] = useState(null);
    const barRef = useRef(null);

    // Close on outside click
    useEffect(() => {
        const handler = (e) => {
            if (barRef.current && !barRef.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    if (!health || health.is_default) return null;

    const { ahead_by, behind_by, base_conflicts, uncommitted_conflicts, default_branch } = health;
    const baseConflictFiles = Object.entries(base_conflicts || {});
    const uncommittedFiles = Object.entries(uncommitted_conflicts || {});
    
    const hasBaseConflicts = baseConflictFiles.length > 0;
    const hasUncommitted = uncommittedFiles.length > 0;
    const hasAnyConflicts = hasBaseConflicts || hasUncommitted;
    
    // Determine overall status visually
    const statusColor = loading ? '#555' : hasAnyConflicts ? '#f59e0b' : '#34d399';
    
    // Label for the trigger pill
    let statusLabel = 'up to date';
    if (loading) statusLabel = 'checking...';
    else if (hasAnyConflicts) {
        const total = baseConflictFiles.length + uncommittedFiles.length;
        statusLabel = `${total} conflict${total !== 1 ? 's' : ''}`;
    }

    return (
        <div ref={barRef} style={{ position: 'relative', flexShrink: 0 }}>
            {/* Trigger pill in header */}
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    display: 'flex', alignItems: 'center', gap: 7,
                    background: open ? '#111' : 'transparent',
                    border: `1px solid ${open ? '#333' : 'transparent'}`,
                    borderRadius: 6, padding: '4px 10px',
                    cursor: 'pointer', transition: 'all 0.15s',
                    fontFamily: '"Geist Mono", "JetBrains Mono", monospace',
                }}
                onMouseEnter={e => { if (!open) { e.currentTarget.style.background = '#0a0a0a'; e.currentTarget.style.borderColor = '#222'; } }}
                onMouseLeave={e => { if (!open) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'transparent'; } }}
            >
                <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: statusColor,
                    boxShadow: loading ? 'none' : `0 0 5px ${statusColor}99`,
                    flexShrink: 0,
                }} />
                <span style={{ fontSize: 10, color: '#888', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
                    vs {default_branch}
                </span>
                <span style={{ fontSize: 10, color: statusColor, letterSpacing: '0.03em', whiteSpace: 'nowrap' }}>
                    {statusLabel}
                </span>
                {!loading && (
                    <span style={{ fontSize: 8, color: '#444', marginLeft: 2 }}>{open ? '▴' : '▾'}</span>
                )}
            </button>

            {/* Dropdown panel */}
            {open && !loading && (
                <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', right: 0,
                    background: '#0a0a0a',
                    border: `1px solid ${hasAnyConflicts ? '#2a1f0a' : '#1a2a1a'}`,
                    borderRadius: 8,
                    minWidth: 340, maxWidth: 440,
                    boxShadow: '0 12px 40px rgba(0,0,0,0.9)',
                    zIndex: 100,
                    fontFamily: '"Geist Mono", "JetBrains Mono", monospace',
                    overflow: 'hidden',
                }}>
                    {/* Summary row */}
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 16,
                        padding: '10px 14px',
                        borderBottom: '1px solid #1a1a1a',
                    }}>
                        <span style={{ fontSize: 10, color: '#555' }}>
                            <span style={{ color: '#888' }}>⬆</span> {ahead_by} ahead
                        </span>
                        <span style={{ fontSize: 10, color: '#555' }}>
                            <span style={{ color: '#888' }}>⬇</span> {behind_by} behind
                        </span>
                        {!hasAnyConflicts && (
                            <span style={{ fontSize: 10, color: '#34d399', marginLeft: 'auto' }}>all clear</span>
                        )}
                    </div>

                    <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                        {/* Base Conflicts */}
                        {hasBaseConflicts && (
                            <div style={{ padding: '6px 0', borderBottom: hasUncommitted ? '1px solid #1a1a1a' : 'none' }}>
                                <div style={{ padding: '4px 14px', fontSize: 9, color: '#888', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                    Base Conflicts
                                </div>
                                {baseConflictFiles.map(([filename, ranges]) => {
                                    const basename = filename.split('/').pop();
                                    const isExpanded = expandedFile === `base-${filename}`;
                                    const totalLines = ranges.reduce((sum, [s, e]) => sum + (e - s), 0);
                                    return (
                                        <div key={`base-${filename}`}>
                                            <div
                                                onClick={() => setExpandedFile(isExpanded ? null : `base-${filename}`)}
                                                style={{
                                                    display: 'flex', alignItems: 'center',
                                                    justifyContent: 'space-between',
                                                    padding: '6px 14px', cursor: 'pointer',
                                                    transition: 'background 0.1s',
                                                }}
                                                onMouseEnter={e => e.currentTarget.style.background = '#111'}
                                                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                                                    <span style={{ fontSize: 8, color: '#555', flexShrink: 0 }}>{isExpanded ? '▾' : '▸'}</span>
                                                    <span style={{
                                                        fontSize: 10, color: '#bbb',
                                                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                                    }} title={filename}>{basename}</span>
                                                    <span style={{ fontSize: 9, color: '#555', whiteSpace: 'nowrap', flexShrink: 0 }}>{filename.includes('/') ? filename.replace('/' + basename, '') : ''}</span>
                                                </div>
                                                <span style={{
                                                    fontSize: 9, color: '#f59e0b',
                                                    background: '#f59e0b14', border: '1px solid #f59e0b2a',
                                                    borderRadius: 4, padding: '1px 6px',
                                                    flexShrink: 0, marginLeft: 10,
                                                }}>~{totalLines} lines</span>
                                            </div>

                                            {isExpanded && (
                                                <div style={{ padding: '2px 14px 8px 30px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                                                    {ranges.map(([s, e], i) => (
                                                        <div key={i} style={{
                                                            fontSize: 9, color: '#666',
                                                            fontVariantNumeric: 'tabular-nums',
                                                            display: 'flex', alignItems: 'center', gap: 6,
                                                        }}>
                                                            <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#f59e0b55', flexShrink: 0 }} />
                                                            lines {s}–{e - 1} <span style={{ color: '#444' }}>({e - s} changed)</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {/* Uncommitted Live Conflicts */}
                        {hasUncommitted && (
                            <div style={{ padding: '6px 0' }}>
                                <div style={{ padding: '4px 14px', fontSize: 9, color: '#888', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                                    Uncommitted Conflicts
                                </div>
                                {uncommittedFiles.map(([filename, ranges]) => {
                                    const basename = filename.split('/').pop();
                                    const isExpanded = expandedFile === `live-${filename}`;
                                    const totalLines = ranges.reduce((sum, [s, e]) => sum + (e - s), 0);
                                    return (
                                        <div key={`live-${filename}`}>
                                            <div
                                                onClick={() => setExpandedFile(isExpanded ? null : `live-${filename}`)}
                                                style={{
                                                    display: 'flex', alignItems: 'center',
                                                    justifyContent: 'space-between',
                                                    padding: '6px 14px', cursor: 'pointer',
                                                    transition: 'background 0.1s',
                                                }}
                                                onMouseEnter={e => e.currentTarget.style.background = '#111'}
                                                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                                                    <span style={{ fontSize: 8, color: '#555', flexShrink: 0 }}>{isExpanded ? '▾' : '▸'}</span>
                                                    <span style={{
                                                        fontSize: 10, color: '#bbb',
                                                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                                    }} title={filename}>{basename}</span>
                                                    <span style={{ fontSize: 9, color: '#555', whiteSpace: 'nowrap', flexShrink: 0 }}>{filename.includes('/') ? filename.replace('/' + basename, '') : ''}</span>
                                                </div>
                                                <span style={{
                                                    fontSize: 9, color: '#f59e0b',
                                                    background: '#f59e0b14', border: '1px solid #f59e0b2a',
                                                    borderRadius: 4, padding: '1px 6px',
                                                    flexShrink: 0, marginLeft: 10,
                                                }}>~{totalLines} lines</span>
                                            </div>

                                            {isExpanded && (
                                                <div style={{ padding: '2px 14px 8px 30px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                                                    {ranges.map(([s, e], i) => (
                                                        <div key={i} style={{
                                                            fontSize: 9, color: '#666',
                                                            fontVariantNumeric: 'tabular-nums',
                                                            display: 'flex', alignItems: 'center', gap: 6,
                                                        }}>
                                                            <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#ef444455', flexShrink: 0 }} />
                                                            lines {s}–{e - 1} <span style={{ color: '#444' }}>({e - s} changed)</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

// ─── Search Bar ───────────────────────────────────────────────────────────────

const SearchBar = ({ nodes, onFocus }) => {
    const [query, setQuery] = useState('');
    const [open, setOpen] = useState(false);
    const results = useMemo(() => {
        if (!query.trim()) return [];
        return nodes
            .filter(n => n.type !== 'rootNode' && n.data.label.toLowerCase().includes(query.toLowerCase()))
            .slice(0, 8);
    }, [query, nodes]);

    return (
        <div style={{ position: 'relative', width: 240 }}>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: '#0a0a0a', border: '1px solid #333333',
                borderRadius: 8, padding: '6px 10px',
            }}>
                <svg width="12" height="12" fill="none" stroke="#888888" strokeWidth="2" viewBox="0 0 24 24">
                    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                    value={query}
                    onChange={e => { setQuery(e.target.value); setOpen(true); }}
                    onFocus={() => setOpen(true)}
                    onBlur={() => setTimeout(() => setOpen(false), 150)}
                    placeholder="Search files..."
                    style={{
                        background: 'transparent', border: 'none', outline: 'none',
                        color: '#ededed', fontSize: 11, fontFamily: 'inherit', width: '100%',
                    }}
                />
            </div>
            {open && results.length > 0 && (
                <div style={{
                    position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
                    background: '#0a0a0a', border: '1px solid #333333', borderRadius: 8,
                    overflow: 'hidden', zIndex: 50, boxShadow: '0 8px 32px rgba(0,0,0,0.9)',
                }}>
                    {results.map(n => (
                        <div
                            key={n.id}
                            onMouseDown={() => { onFocus(n.id); setQuery(''); setOpen(false); }}
                            style={{
                                padding: '6px 12px', cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: 8,
                                fontSize: 11, color: '#888', fontFamily: 'inherit',
                                borderBottom: '1px solid #1a1a1a',
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = '#111111'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >
                            {n.type === 'folderNode'
                                ? <span style={{ color: '#888888' }}><FolderIcon /></span>
                                : getFileIcon(n.data.label)}
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#bbb' }}>
                                {n.data.label}
                            </span>
                            <span style={{ color: '#555', fontSize: 9, marginLeft: 'auto' }}>
                                {n.type === 'folderNode' ? 'dir' : ''}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

// ─── Stats Bar ────────────────────────────────────────────────────────────────

const StatsBar = ({ nodes }) => {
    const folders = nodes.filter(n => n.type === 'folderNode').length;
    const files   = nodes.filter(n => n.type === 'fileNode').length;
    return (
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#555', fontFamily: 'monospace' }}>
                <span style={{ color: '#888' }}>{folders}</span> dirs
            </span>
            <span style={{ fontSize: 10, color: '#555', fontFamily: 'monospace' }}>
                <span style={{ color: '#555' }}>{files}</span> files
            </span>
        </div>
    );
};

// ─── Flow Inner ───────────────────────────────────────────────────────────────

const FlowInner = ({ fileTree, repoData, loading, error }) => {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [expandedFolders, setExpandedFolders] = useState(new Set());
    const { fitView, setCenter, getNode } = useReactFlow();
    const initialized = useRef(false);

    const focusNode = useCallback((nodeId) => {
        const node = getNode(nodeId);
        if (node) {
            const w = node.type === 'rootNode' ? ROOT_R * 2 : node.type === 'folderNode' ? FOLDER_W : NODE_W;
            const h = node.type === 'rootNode' ? ROOT_R * 2 : node.type === 'folderNode' ? FOLDER_H : NODE_H;
            setCenter(node.position.x + w / 2, node.position.y + h / 2, { zoom: 1.6, duration: 600 });
        }
    }, [getNode, setCenter]);

    const toggleFolder = useCallback((folderId) => {
        setExpandedFolders(prev => {
            const next = new Set(prev);
            if (next.has(folderId)) next.delete(folderId);
            else next.add(folderId);
            return next;
        });
    }, []);

    useEffect(() => {
        if (!fileTree || initialized.current) return;
        initialized.current = true;
        const initial = new Set();
        Object.values(fileTree.children).forEach(child => {
            if (child.type === 'folder') initial.add(child.id);
        });
        setExpandedFolders(initial);
    }, [fileTree]);

    useEffect(() => {
        if (!fileTree) return;
        const { nodes: rawNodes, edges: rawEdges } = generateGraph(fileTree, expandedFolders);
        const enrichedNodes = rawNodes.map(n =>
            n.type === 'folderNode'
                ? { ...n, data: { ...n.data, onToggle: toggleFolder } }
                : n
        );
        const layouted = applyForceLayout(enrichedNodes, rawEdges);
        setNodes(layouted);
        setEdges(rawEdges);
        setTimeout(() => fitView({ padding: 0.18, duration: 500 }), 60);
    }, [fileTree, expandedFolders, toggleFolder, setNodes, setEdges, fitView]);

    if (loading) {
        return (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000000' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
                    <div style={{
                        width: 28, height: 28, border: '2px solid #333333',
                        borderTop: '2px solid #ededed', borderRadius: '50%',
                        animation: 'spin 0.9s linear infinite',
                    }} />
                    <span style={{ color: '#555555', fontSize: 11, fontFamily: 'monospace', letterSpacing: '0.08em' }}>
                        loading repository...
                    </span>
                </div>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    if (error || !repoData) {
        return (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000000' }}>
                <div style={{ textAlign: 'center', padding: 32, border: '1px solid #2a0a0a', borderRadius: 12 }}>
                    <p style={{ color: '#f87171', fontSize: 13, marginBottom: 8 }}>Error loading repository</p>
                    <p style={{ color: '#555555', fontSize: 11, fontFamily: 'monospace' }}>{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div style={{ flex: 1, position: 'relative', background: '#000000' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
                minZoom={0.04}
                maxZoom={3}
                proOptions={{ hideAttribution: true }}
                style={{ background: '#000000' }}
            >
                <Panel position="top-left" style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '12px 16px' }}>
                    <SearchBar nodes={nodes} onFocus={focusNode} />
                    <StatsBar nodes={nodes} />
                </Panel>
                <Panel position="bottom-left" style={{ margin: '0 16px 12px' }}>
                    <span style={{ fontSize: 10, color: '#333333', fontFamily: 'monospace' }}>
                        click folders to expand · scroll to zoom · drag to pan
                    </span>
                </Panel>
                <Background color="#111111" gap={36} size={1} variant="dots" />
                <Controls
                    style={{
                        background: '#0a0a0a', border: '1px solid #333333',
                        borderRadius: 8, overflow: 'hidden',
                        boxShadow: '0 4px 16px rgba(0,0,0,0.8)',
                    }}
                    showInteractive={false}
                />
                <MiniMap
                    style={{
                        background: '#0a0a0a', border: '1px solid #333333',
                        borderRadius: 8, overflow: 'hidden',
                    }}
                    nodeColor={n => {
                        if (n.type === 'rootNode') return '#ededed';
                        if (n.type === 'folderNode') return '#444444';
                        return '#1a1a1a';
                    }}
                    maskColor="rgba(0,0,0,0.75)"
                />
            </ReactFlow>
        </div>
    );
};

// ─── Main Page ────────────────────────────────────────────────────────────────

const RepoDetailsPage = () => {
    const { repoId } = useParams();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const branchParam = searchParams.get('branch');

    const [loading, setLoading] = useState(true);
    const [error, setError]     = useState(null);
    const [repoData, setRepoData] = useState(null);
    const [fileTree, setFileTree] = useState(null);
    const [branchHealth, setBranchHealth] = useState(null);
    const [healthLoading, setHealthLoading] = useState(false);

    useEffect(() => {
        setLoading(true);
        getRepoDetails(repoId, branchParam)
            .then(data => {
                setRepoData(data);
                setFileTree(buildTree(data.files || []));
            })
            .catch(err => setError(err.message || 'Failed to fetch repository details'))
            .finally(() => setLoading(false));
    }, [repoId, branchParam]);

    // Fetch branch health snapshot whenever the active branch changes
    useEffect(() => {
        if (!repoData) return;
        const activeBranch = repoData.active_branch?.name;
        const defaultBranch = repoData.repo?.default_branch;
        if (!activeBranch || activeBranch === defaultBranch) {
            setBranchHealth({ is_default: true });
            return;
        }
        setHealthLoading(true);
        getBranchHealth(repoId, activeBranch)
            .then(data => setBranchHealth(data))
            .catch(() => setBranchHealth(null))
            .finally(() => setHealthLoading(false));
    }, [repoId, repoData]);

    const handleBranchChange = (e) => setSearchParams({ branch: e.target.value });

    return (
        <div style={{
            height: '100vh', width: '100%',
            background: '#000000', color: '#ededed',
            display: 'flex', flexDirection: 'column',
            fontFamily: 'ui-sans-serif, system-ui, -apple-system, sans-serif',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0 20px', height: 48,
                borderBottom: '1px solid #333333',
                background: '#000000', flexShrink: 0, zIndex: 10,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button
                        onClick={() => navigate('/repos')}
                        style={{
                            background: 'transparent', border: 'none', cursor: 'pointer',
                            color: '#888888', padding: 6, borderRadius: 6,
                            display: 'flex', alignItems: 'center', transition: 'color 0.15s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.color = '#ffffff'}
                        onMouseLeave={e => e.currentTarget.style.color = '#888888'}
                        title="Back to Repos"
                    >
                        <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                        </svg>
                    </button>
                    <div style={{ width: 1, height: 16, background: '#333333' }} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="#ededed" style={{ opacity: 0.7 }}>
                            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                        </svg>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#ededed', letterSpacing: '0.02em' }}>
                            {repoData ? ((repoData.repo.name || '').split('/')[1] || repoData.repo.name) : '—'}
                        </span>
                    </div>
                    {repoData?.active_branch?.name && (
                        <>
                            <div style={{ width: 1, height: 12, background: '#333333' }} />
                            <span style={{ fontSize: 11, color: '#888888', letterSpacing: '0.03em' }}>
                                {repoData.active_branch.name}
                            </span>
                        </>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    {repoData?.active_branch?.updated_at && (
                        <span style={{ fontSize: 10, color: '#555555', letterSpacing: '0.03em' }}>
                            updated {new Date(repoData.active_branch.updated_at).toLocaleDateString()}
                        </span>
                    )}
                    {repoData?.branches && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 10, color: '#555555' }}>branch</span>
                            <select
                                style={{
                                    background: '#0a0a0a', border: '1px solid #333333',
                                    color: '#ededed', fontSize: 11, borderRadius: 6,
                                    padding: '3px 8px', outline: 'none', cursor: 'pointer',
                                    fontFamily: 'inherit',
                                }}
                                value={repoData.active_branch?.id || ''}
                                onChange={handleBranchChange}
                            >
                                {repoData.branches.map(b => (
                                    <option key={b.id} value={b.id}>{b.name}</option>
                                ))}
                            </select>
                        </div>
                    )}
                    <BranchHealthBar health={healthLoading ? null : branchHealth} loading={healthLoading} />
                </div>
            </div>

            {/* Canvas */}
            <ReactFlowProvider>
                <FlowInner
                    fileTree={fileTree}
                    repoData={repoData}
                    loading={loading}
                    error={error}
                />
            </ReactFlowProvider>
        </div>
    );
};

export default RepoDetailsPage;