import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { getUserRepos, BACK_URL } from '../api';

const ReposPage = () => {
    const [repos, setRepos] = useState([]);
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        setLoading(true);
        getUserRepos()
            .then(data => {
                setRepos(data.repos || []);
                setUser(data.user || null);
            })
            .catch(err => {
                setError(err.response?.status === 401
                    ? 'Unauthorized. Please log in again.'
                    : err.message);
            })
            .finally(() => setLoading(false));
    }, []);

    const filteredRepos = useMemo(() => {
        if (!searchQuery) return repos;
        return repos.filter(repo =>
            repo.name.toLowerCase().includes(searchQuery.toLowerCase())
        );
    }, [repos, searchQuery]);

    // Navigate to the permission explainer / install page.
    // Pass the user's personal GitHub ID so ConnectRepoPage can set target_id
    // in the GitHub install URL (pre-selects personal account over org).
    const handleConnectRepo = () => {
        const params = new URLSearchParams(
            user?.github_id ? { uid: user.github_id } : {}
        );
        navigate(`/connect${params.toString() ? `?${params}` : ''}`);
    };

    return (
        <div className="min-h-screen bg-[#000] text-[#ededed] font-sans flex flex-col">
            {/* Navbar */}
            <nav className="flex items-center justify-between px-6 py-4 border-b border-[#333]">
                <div className="flex items-center space-x-3">
                    {user && (
                        <>
                            {user.avatar_url && (
                                <img src={user.avatar_url} alt="avatar" className="w-7 h-7 rounded-full border border-[#333]" />
                            )}
                            <span className="text-sm font-medium tracking-wide">{user.login}</span>
                            <span className="text-[#555] px-1">/</span>
                            <span className="text-sm text-[#ededed]">Repositories</span>
                        </>
                    )}
                </div>
                <a href={`${BACK_URL}auth/logout`} className="text-sm text-[#888] hover:text-[#fff] transition-colors">
                    Logout
                </a>
            </nav>

            {/* Main */}
            <main className="flex-1 w-full max-w-5xl mx-auto px-6 py-12 space-y-8">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight">Connected Repositories</h1>
                        <p className="text-[#888] text-sm mt-1">Repositories monitored by CodeSync.</p>
                    </div>
                    <button
                        onClick={handleConnectRepo}
                        className="flex items-center space-x-2 px-4 py-2.5 bg-[#ededed] text-[#000] text-sm font-semibold rounded-md hover:bg-white transition-colors"
                    >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span>Manage Repos</span>
                    </button>
                </div>

                {/* Admin Notice */}
                <div className="bg-[#0a0a0a] border border-[#333] rounded-lg p-4 flex items-start space-x-3">
                    <svg className="w-5 h-5 text-[#888] shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div>
                        <p className="text-sm font-medium text-[#ededed]">Admin rights required</p>
                        <p className="text-sm text-[#888] mt-1">
                            You must be a repository admin on GitHub to add or remove it from CodeSync monitoring.
                            Regular collaborators will gain access here automatically once an admin connects it.
                        </p>
                    </div>
                </div>

                {/* Search (only when there are repos) */}
                {repos.length > 0 && (
                    <div className="relative">
                        <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#888]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        <input
                            type="text"
                            placeholder="Search connected repos..."
                            className="w-full bg-[#0a0a0a] border border-[#333] rounded-md py-2.5 pl-10 pr-4 text-sm focus:outline-none focus:border-[#555] transition-colors placeholder-[#555]"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                        />
                    </div>
                )}

                {/* Body */}
                {loading ? (
                    <div className="flex items-center justify-center py-32">
                        <div className="w-5 h-5 border-2 border-transparent border-t-[#ededed] rounded-full animate-spin" />
                    </div>
                ) : error ? (
                    <div className="text-center py-16 rounded-xl bg-[#0a0a0a] border border-red-900/40">
                        <p className="text-red-400 font-medium">Error</p>
                        <p className="text-[#888] text-sm mt-2">{error}</p>
                    </div>
                ) : repos.length === 0 ? (
                    /* Empty state */
                    <div className="flex flex-col items-center justify-center py-28 border border-[#333] border-dashed rounded-xl space-y-6">
                        <div className="text-center space-y-2">
                            <svg className="w-10 h-10 text-[#333] mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                            <p className="text-[#888] text-sm">No repositories connected yet.</p>
                            <p className="text-[#555] text-xs">Install the CodeSync GitHub App on a repository to get started.</p>
                        </div>
                        <button
                            onClick={handleConnectRepo}
                            className="flex items-center space-x-2 px-5 py-2.5 bg-[#ededed] text-[#000] text-sm font-semibold rounded-md hover:bg-white transition-colors"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                            <span>Manage Repos</span>
                        </button>
                    </div>
                ) : filteredRepos.length === 0 ? (
                    <div className="text-center py-24 border border-[#333] border-dashed rounded-xl">
                        <p className="text-[#888] text-sm">No repositories match your search.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {filteredRepos.map(repo => (
                            <div
                                key={repo.id}
                                onClick={() => navigate(`/repos/${repo.id}`)}
                                className="bg-[#0a0a0a] border border-[#333] rounded-lg p-5 flex flex-col justify-between hover:border-[#555] transition-colors cursor-pointer"
                            >
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-2.5 overflow-hidden">
                                            <svg className="w-5 h-5 text-[#ededed] flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                                                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                                            </svg>
                                            <a
                                                href={repo.html_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-sm font-semibold hover:underline truncate"
                                            >
                                                {(repo.name || '').split('/')[1] || repo.name || 'Unknown'}
                                            </a>
                                        </div>
                                        {repo.private && (
                                            <span className="flex-shrink-0 ml-2 px-2 py-0.5 rounded-full border border-[#333] text-[10px] font-medium text-[#888] uppercase tracking-wider">
                                                Private
                                            </span>
                                        )}
                                    </div>
                                    {repo.description && (
                                        <p className="text-xs text-[#888] line-clamp-2">{repo.description}</p>
                                    )}
                                </div>
                                <div className="mt-6 flex items-center space-x-4 text-xs text-[#555]">
                                    {repo.language && (
                                        <span className="flex items-center space-x-1.5">
                                            <span className="w-2 h-2 rounded-full bg-[#ededed]" />
                                            <span>{repo.language}</span>
                                        </span>
                                    )}
                                    {repo.updated_at && (
                                        <span>
                                            {new Date(repo.updated_at).toLocaleDateString(undefined, {
                                                month: 'short', day: 'numeric', year: 'numeric',
                                            })}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};

export default ReposPage;
