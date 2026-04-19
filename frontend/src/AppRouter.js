import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import App from './App';
import api from './api';
import ReposPage from './pages/ReposPage';
import ConnectRepoPage from './pages/ConnectRepoPage';
import RepoDetailsPage from './pages/RepoDetailsPage';
import RootPage from './pages/RootPage';

const PrivateRoute = ({ children }) => {
    const [isLoggedIn, setIsLoggedIn] = React.useState(null);

    React.useEffect(() => {
        api.get('user/repos')
            .then(() => setIsLoggedIn(true))
            .catch(() => setIsLoggedIn(false));
    }, []);

    if (isLoggedIn === null) {
        return <div className="min-h-screen bg-black flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-transparent border-t-white rounded-full animate-spin"></div>
        </div>;
    }

    return isLoggedIn ? children : <Navigate to="/" />;
};

const AppRouter = () => {
    return (
        <Router>
            <Routes>
                <Route path="/repos" element={
                    <PrivateRoute>
                        <ReposPage />
                    </PrivateRoute>
                } />
                <Route path="/connect" element={
                    <PrivateRoute>
                        <ConnectRepoPage />
                    </PrivateRoute>
                } />
                <Route path="/repos/:repoId" element={
                    <PrivateRoute>
                        <RepoDetailsPage />
                    </PrivateRoute>
                } />
                <Route path="/flow" element={<App />} />
                <Route path="/" element={<RootPage />} />
                <Route path="*" element={<Navigate to="/" />} />
            </Routes>
        </Router>
    );
};

export default AppRouter;
