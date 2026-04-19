import axios from 'axios';

// In Create React App, environment variables must start with REACT_APP_
export const BACK_URL = process.env.REACT_APP_BACK_URL;

const api = axios.create({
    baseURL: BACK_URL,
    withCredentials: true, // Crucial for sending/receiving HttpOnly cookies
});

export const loginWithGithub = () => {
    window.location.href = `${BACK_URL}auth/github`;
};

export const getUserRepos = async () => {
    const response = await api.get('user/repos');
    return response.data;
};

export const getRepoDetails = async (repoId, branchId = null) => {
    const params = branchId ? `?branch_id=${branchId}` : '';
    const response = await api.get(`user/repos/${repoId}${params}`);
    return response.data;
};

export const getBranchHealth = async (repoId, branchName) => {
    const response = await api.get(`user/repos/${repoId}/branch-health`, {
        params: { branch_name: branchName },
    });
    return response.data;
};

export default api;