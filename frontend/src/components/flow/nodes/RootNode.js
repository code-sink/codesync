import React from 'react';
import { Handle, Position } from 'reactflow';
import { ROOT_R } from '../../../constants/flowConstants';

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

export default RootNode;