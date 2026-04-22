import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ReactFlowProvider } from 'reactflow';
import { getRepoDetails, getBranchHealth } from '../api';

import FlowInner from '../components/flow/FlowInner';
import BranchHealthBar from '../components/ui/BranchHealthBar';
import { buildTree } from '../utils/graphHelpers';
import { useActiveViewers } from '../hooks/useActiveViewers';
import { ViewerStack } from '../components/ui/ViewerStack';

const RepoDetailsPage = () => {
    const { repoId } = useParams();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const branchParam = searchParams.get('branch');

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [repoData, setRepoData] = useState(null);
    const [fileTree, setFileTree] = useState(null);
    const [branchHealth, setBranchHealth] = useState(null);
    const [healthLoading, setHealthLoading] = useState(false);
    const [activeFileId, setActiveFileId] = useState('file_src_app_js');

    // This will automatically update when the file changes
    const activeUsers = useActiveViewers(activeFileId);

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
                    <ViewerStack users={activeUsers} />
                    <div style={{ width: 1, height: 16, background: '#333333' }} />
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