import React from 'react';
import { Handle, Position } from 'reactflow';
import { FOLDER_W, FOLDER_H } from '../../../constants/flowConstants';
import { FolderIcon } from '../../../utils/iconHelpers';

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

export default FolderNode;