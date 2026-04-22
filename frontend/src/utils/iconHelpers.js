import React from 'react';

export const FolderIcon = ({ open }) => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
        {!open && <><line x1="12" y1="11" x2="12" y2="17" /><line x1="9" y1="14" x2="15" y2="14" /></>}
    </svg>
);

export const getFileColor = (name) => {
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

export const getFileIcon = (name) => {
    const color = getFileColor(name);
    return (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" />
            <polyline points="13 2 13 9 20 9" />
        </svg>
    );
};