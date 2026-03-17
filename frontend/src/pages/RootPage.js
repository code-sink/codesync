import React from 'react';
import { Navigate } from 'react-router-dom';
import api, { loginWithGithub } from '../api';

const RootPage = () => {
    const [isLoggedIn, setIsLoggedIn] = React.useState(null);

    React.useEffect(() => {
        api.get('/user/repos')
            .then(() => setIsLoggedIn(true))
            .catch(() => setIsLoggedIn(false));
    }, []);

    if (isLoggedIn === null) {
        return <div className="min-h-screen bg-[#000] flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-transparent border-t-[#fff] rounded-full animate-spin"></div>
        </div>;
    }

    if (isLoggedIn) {
        return <Navigate to="/repos" />;
    }

    return (
        <div className="flex flex-col min-h-screen bg-[#000] text-[#fff] font-sans selection:bg-[#fff] selection:text-[#000]">
            {/* Minimal Header */}
            <header className="flex items-center justify-between px-8 py-4 border-b border-[#222]">
                <div className="flex items-center space-x-3">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                    </svg>
                    <span className="text-xl font-medium tracking-tight">CodeSync</span>
                </div>
                <button
                    onClick={loginWithGithub}
                    className="flex items-center space-x-2 px-4 py-2 bg-[#111] border border-[#333] hover:bg-[#222] text-sm text-[#fff] rounded-md transition-colors"
                >
                    <span>Login</span>
                </button>
            </header>

            {/* Hero Section */}
            <main className="flex-1 flex flex-col items-center justify-center p-8">
                <div className="max-w-xl text-center space-y-8">
                    <div className="space-y-4">
                        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight">
                            Orchestrate your code.
                        </h1>
                        <p className="text-lg text-[#aaa] font-light max-w-md mx-auto">
                            Connect your repositories to visualize structure, track changes, and synchronize effortlessly.
                        </p>
                    </div>

                    <div className="pt-4">
                        <button
                            onClick={loginWithGithub}
                            className="inline-flex items-center justify-center space-x-3 px-6 py-3 bg-[#fff] text-[#000] text-sm font-medium rounded-lg hover:bg-[#ccc] transition-colors focus:outline-none"
                        >
                            <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current">
                                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                            </svg>
                            <span>Continue with GitHub</span>
                        </button>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default RootPage;
