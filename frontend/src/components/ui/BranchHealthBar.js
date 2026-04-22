import React, { useState, useEffect, useRef } from 'react';

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

export default BranchHealthBar;