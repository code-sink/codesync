import React, { useState, useMemo } from 'react';
import { FolderIcon, getFileIcon } from '../../utils/iconHelpers';

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

export default SearchBar;