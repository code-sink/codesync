import React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

/**
 * ConnectRepoPage — generic permission explainer.
 *
 * Reached via: navigate('/connect?uid=<user_github_id>')
 *
 * Explains what the code-sink GitHub App does, then sends the user to
 * github.com/apps/code-sink/installations/new with:
 *   - target_id = user's personal GitHub ID  (pre-selects personal account)
 *   - target_type = User
 *
 * After installing, GitHub fires an `installation` webhook to our backend
 * which upserts the repo, syncs collaborators, and populates branches/files.
 */
const ConnectRepoPage = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();

    // The logged-in user's personal GitHub ID — pre-selects their personal
    // account on the GitHub install page instead of the code-sink org.
    const userGithubId = searchParams.get('uid') || '';

    const handleInstall = () => {
        const params = new URLSearchParams({
            ...(userGithubId ? { target_id: userGithubId, target_type: 'User' } : {}),
        });
        const qs = params.toString();
        const url = `https://github.com/apps/code-sink/installations/new${qs ? `?${qs}` : ''}`;
        window.open(url, '_blank', 'noopener,noreferrer');
    };

    const permissions = [
        {
            icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
            ),
            title: 'Push events',
            description: 'Whenever code is pushed to a branch, CodeSync updates its file tree — additions and deletions, across every branch automatically.',
        },
        {
            icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
            ),
            title: 'Collaborator changes',
            description: 'When a collaborator is removed on GitHub, CodeSync immediately revokes their access so your history stays private.',
        },
        {
            icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
            ),
            title: 'Repository contents (read-only)',
            description: 'CodeSync reads your file tree and branch list once at install to build the initial snapshot. It never writes to your repo.',
        },
        {
            icon: (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
            ),
            title: 'No write access, ever',
            description: 'CodeSync will never push commits, open PRs, or change anything in your repository.',
        },
    ];

    return (
        <div className="min-h-screen bg-[#000] text-[#ededed] font-sans flex flex-col">
            {/* Navbar */}
            <nav className="flex items-center px-6 py-4 border-b border-[#333]">
                <button
                    onClick={() => navigate('/repos')}
                    className="flex items-center space-x-2 text-sm text-[#888] hover:text-[#ededed] transition-colors"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                    </svg>
                    <span>Back</span>
                </button>
            </nav>

            {/* Main */}
            <main className="flex-1 flex items-start justify-center px-6 py-16">
                <div className="w-full max-w-xl space-y-10">

                    {/* Header */}
                    <div className="space-y-3">
                        <h1 className="text-2xl font-semibold tracking-tight">Manage GitHub Integrations</h1>
                        <p className="text-sm text-[#888] leading-relaxed">
                            Install the <span className="text-[#ededed] font-medium">code-sink</span> GitHub App
                            on your repository. Here's exactly what access it needs and how your data is used:
                        </p>
                    </div>

                    {/* Permissions */}
                    <div className="border border-[#333] rounded-xl overflow-hidden divide-y divide-[#333]">
                        {permissions.map((perm, i) => (
                            <div key={i} className="flex items-start space-x-4 px-5 py-4">
                                <div className="flex-shrink-0 mt-0.5 text-[#888]">{perm.icon}</div>
                                <div>
                                    <p className="text-sm font-semibold">{perm.title}</p>
                                    <p className="text-sm text-[#888] mt-1 leading-relaxed">{perm.description}</p>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Steps */}
                    <div className="bg-[#0a0a0a] border border-[#333] rounded-xl px-5 py-5 space-y-4">
                        <p className="text-sm font-semibold">What happens next</p>
                        <ol className="space-y-3">
                            {[
                                "You'll be taken to GitHub to install the code-sink App.",
                                "Select your personal account from the account dropdown (not an org).",
                                "Choose \"Only select repositories\" and pick the repos you want to track.",
                                "Click Install — GitHub redirects you back to CodeSync.",
                                "CodeSync reads the file tree, branches, and collaborators automatically.",
                                "Every future push keeps file tracking up to date. Removed collaborators lose access instantly.",
                            ].map((step, i) => (
                                <li key={i} className="flex items-start space-x-3 text-sm text-[#888]">
                                    <span className="flex-shrink-0 w-5 h-5 rounded-full border border-[#444] flex items-center justify-center text-[10px] font-bold text-[#555] mt-0.5">
                                        {i + 1}
                                    </span>
                                    <span className="leading-relaxed">{step}</span>
                                </li>
                            ))}
                        </ol>
                    </div>

                    {/* CTA */}
                    <div className="flex items-center space-x-4">
                        <button
                            onClick={handleInstall}
                            className="flex items-center space-x-2 px-6 py-3 bg-[#ededed] text-[#000] text-sm font-semibold rounded-lg hover:bg-white transition-colors"
                        >
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                            </svg>
                            <span>Manage on GitHub</span>
                        </button>
                        <button
                            onClick={() => navigate('/repos')}
                            className="px-4 py-3 text-sm text-[#888] hover:text-[#ededed] transition-colors"
                        >
                            Cancel
                        </button>
                    </div>

                    <p className="text-xs text-[#555]">
                        The app can be uninstalled at any time from{' '}
                        <a href="https://github.com/settings/installations" target="_blank" rel="noopener noreferrer" className="underline hover:text-[#888] transition-colors">
                            github.com/settings/installations
                        </a>.
                    </p>
                </div>
            </main>
        </div>
    );
};

export default ConnectRepoPage;
