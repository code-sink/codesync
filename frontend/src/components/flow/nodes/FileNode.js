import React from 'react';
import { Handle, Position } from 'reactflow';
import { NODE_W, NODE_H } from '../../../constants/flowConstants';
import { getFileColor, getFileIcon } from '../../../utils/iconHelpers';

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

export default FileNode;