import React, { useState, useEffect, useCallback, useRef } from 'react';
import ReactFlow, { Background, Controls, MiniMap, useNodesState, useEdgesState, useReactFlow, Panel } from 'reactflow';
import 'reactflow/dist/style.css';

import { generateGraph, applyForceLayout } from '../../utils/graphHelpers';
import RootNode from './nodes/RootNode';
import FolderNode from './nodes/FolderNode';
import FileNode from './nodes/FileNode';
import FloralEdge from './edges/FloralEdge';
import SearchBar from '../ui/SearchBar';
import StatsBar from '../ui/StatsBar';
import { ROOT_R, FOLDER_W, NODE_W, FOLDER_H, NODE_H } from '../../constants/flowConstants';

const nodeTypes = { rootNode: RootNode, folderNode: FolderNode, fileNode: FileNode };
const edgeTypes = { floralEdge: FloralEdge };

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

export default FlowInner;