import React from 'react';

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

export default StatsBar;