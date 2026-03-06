import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { getRepoDetails } from '../api';

// --- Icons ---
const FolderIcon = ({ expanded }) => (
    <svg className="w-4 h-4 text-[#ccc] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        {expanded ? (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
        ) : (
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
        )}
    </svg>
);

const FileIcon = () => (
    <svg className="w-4 h-4 text-[#aaa] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
);

const FolderOutlineIcon = () => (
    <svg className="w-4 h-4 text-[#aaa] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
);


// --- Tree Building ---

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
                    id: currentPath,
                    name: part,
                    type: isFile ? 'file' : 'folder',
                    children: {},
                    path: currentPath,
                };
            }
            current = current.children[part];
        }
    });

    return root;
}

// Sort folders first, then files, alphabetically
const sortNodes = (a, b) => {
    if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
};

// --- Recursive Tree Component ---

const TreeNode = ({ node, level, expandedFolders, toggleFolder }) => {
    const isExpanded = expandedFolders.has(node.id);
    const hasChildren = Object.keys(node.children).length > 0;

    // Sort children
    const sortedChildren = useMemo(() => {
        return Object.values(node.children).sort(sortNodes);
    }, [node.children]);

    if (node.id === 'root') {
        // Render root children directly
        return (
            <div className="w-full">
                {sortedChildren.map(child => (
                    <TreeNode
                        key={child.id}
                        node={child}
                        level={0}
                        expandedFolders={expandedFolders}
                        toggleFolder={toggleFolder}
                    />
                ))}
            </div>
        );
    }

    if (node.type === 'folder') {
        return (
            <div>
                <div
                    className="flex items-center py-1 px-2 hover:bg-[#111] cursor-pointer transition-colors group"
                    style={{ paddingLeft: `${level * 16 + 8}px` }}
                    onClick={() => toggleFolder(node.id)}
                >
                    <div className="mr-1 opacity-90 group-hover:opacity-100">
                        <FolderIcon expanded={isExpanded} />
                    </div>
                    <div className="mr-2 opacity-90 group-hover:opacity-100">
                        <FolderOutlineIcon />
                    </div>
                    <span className="text-sm font-mono text-[#fff] tracking-wide truncate select-none border-b border-transparent group-hover:border-[#fff] pb-[1px]">
                        {node.name}
                    </span>
                </div>
                {isExpanded && hasChildren && (
                    <div className="w-full">
                        {sortedChildren.map(child => (
                            <TreeNode
                                key={child.id}
                                node={child}
                                level={level + 1}
                                expandedFolders={expandedFolders}
                                toggleFolder={toggleFolder}
                            />
                        ))}
                    </div>
                )}
            </div>
        );
    }

    // File node
    return (
        <div
            className="flex items-center py-1 px-2 hover:bg-[#111] transition-colors group"
            style={{ paddingLeft: `${level * 16 + 28}px` }} // +28 to align under folder icons
        >
            <div className="mr-2 opacity-90 group-hover:opacity-100">
                <FileIcon />
            </div>
            <span className="text-sm font-mono text-[#ddd] group-hover:text-[#fff] tracking-wide truncate select-none transition-colors">
                <span className="bg-[#111] group-hover:bg-[#222] border border-[#333] group-hover:border-[#555] px-1.5 py-0.5 rounded-sm">
                    {node.name}
                </span>
            </span>
        </div>
    );
};


const RepoDetailsPage = () => {
    const { repoId } = useParams();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const branchParam = searchParams.get('branch');

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [repoData, setRepoData] = useState(null);

    // Set of folder IDs that are currently expanded
    const [expandedFolders, setExpandedFolders] = useState(new Set());
    // Store the raw parsed tree
    const [fileTree, setFileTree] = useState(null);

    // Fetch data
    useEffect(() => {
        setLoading(true);
        // Use the branch from URL param if available
        getRepoDetails(repoId, branchParam)
            .then(data => {
                setRepoData(data);

                // Process tree
                const tree = buildTree(data.files || []);
                setFileTree(tree);

                // Compute initial expanded state (expand top-level folders by default)
                const initialExpanded = new Set();
                const expandLevel = (node, level) => {
                    if (node.type === 'folder' && level < 1) { // Expand root level folders
                        initialExpanded.add(node.id);
                        Object.values(node.children).forEach(c => expandLevel(c, level + 1));
                    }
                };
                expandLevel(tree, 0);
                setExpandedFolders(initialExpanded);
            })
            .catch(err => setError(err.message || 'Failed to fetch repository details'))
            .finally(() => setLoading(false));
    }, [repoId, branchParam]);

    // Handle folder toggle
    const toggleFolder = useCallback((folderId) => {
        setExpandedFolders(prev => {
            const next = new Set(prev);
            if (next.has(folderId)) {
                next.delete(folderId);
            } else {
                next.add(folderId);
            }
            return next;
        });
    }, []);

    const handleBranchChange = (e) => {
        const newBranchId = e.target.value;
        setSearchParams({ branch: newBranchId });
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-[#000] flex items-center justify-center">
                <div className="w-5 h-5 border-2 border-transparent border-t-[#ededed] rounded-full animate-spin"></div>
            </div>
        );
    }

    if (error || !repoData) {
        return (
            <div className="min-h-screen bg-[#000] text-[#ededed] flex flex-col items-center pt-32">
                <p className="text-red-400 font-medium mb-4">Error loading repository</p>
                <p className="text-[#888] text-sm mb-6">{error}</p>
                <button onClick={() => navigate('/repos')} className="text-sm px-4 py-2 border border-[#333] rounded hover:bg-[#111] transition-colors">
                    Back to Repositories
                </button>
            </div>
        );
    }

    return (
        <div className="h-screen w-full bg-[#000] text-[#fff] flex flex-col font-sans">
            {/* Minimal Header */}
            <div className="flex items-center justify-between px-6 py-3 border-b border-[#222] bg-[#000] z-10 shrink-0">
                <div className="flex items-center space-x-4">
                    <button
                        onClick={() => navigate('/repos')}
                        className="text-[#aaa] hover:text-[#fff] transition-colors flex items-center justify-center p-1 rounded-md hover:bg-[#111]"
                        title="Back to Repos"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
                    </button>
                    <div className="h-4 w-px bg-[#333]"></div>
                    <div className="flex items-center space-x-2">
                        <svg className="w-4 h-4 text-[#aaa]" fill="currentColor" viewBox="0 0 24 24">
                            <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                        </svg>
                        <span className="text-sm font-semibold tracking-wide text-[#fff]">
                            {(repoData.repo.name || '').split('/')[1] || repoData.repo.name}
                        </span>
                    </div>
                </div>

                <div className="flex items-center space-x-4">
                    {repoData.active_branch?.updated_at && (
                        <span className="text-xs text-[#555] font-mono">
                            Last updated: {new Date(repoData.active_branch.updated_at).toLocaleDateString()}
                        </span>
                    )}
                    <div className="flex items-center space-x-3">
                        <span className="text-xs text-[#aaa] font-mono">switch branch</span>
                        <select
                            className="bg-[#000] border border-[#333] text-xs text-[#fff] font-mono rounded px-2 py-1 outline-none focus:border-[#555] transition-colors cursor-pointer min-w-[120px]"
                            value={repoData.active_branch?.id || ''}
                            onChange={handleBranchChange}
                        >
                            {repoData.branches.map(b => (
                                <option key={b.id} value={b.id}>{b.name}</option>
                            ))}
                        </select>
                    </div>
                </div>
            </div>

            {/* VS Code Style File Explorer */}
            <div className="flex-1 w-full bg-[#000] overflow-y-auto py-4">
                <div className="max-w-4xl mx-auto px-4 pl-8">
                    {fileTree && Object.keys(fileTree.children).length > 0 ? (
                        <TreeNode
                            node={fileTree}
                            level={0}
                            expandedFolders={expandedFolders}
                            toggleFolder={toggleFolder}
                        />
                    ) : (
                        <div className="flex items-center justify-center pt-24">
                            <div className="text-center bg-[#0a0a0a] border border-[#222] p-6 rounded-xl">
                                <p className="text-[#888] text-sm">No files found on this branch.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default RepoDetailsPage;
