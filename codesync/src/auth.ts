// authentication with github
import * as vscode from 'vscode';

export class AuthManager {
    constructor(private context: vscode.ExtensionContext) {}

    async getToken(): Promise<string | null> {
        const token = await this.context.secrets.get('github_token');
        return token ?? null;
    }

    async authenticate(): Promise<string | null> {
        // built-in GitHub authentication
        const session = await vscode.authentication.getSession(
            'github',
            ['repo', 'user:email'],
            { createIfNone: true }
        );

        if (session) {
            await this.context.secrets.store('github_token', session.accessToken);
            return session.accessToken;
        }

        return null;
    }

    async logout() {
        await this.context.secrets.delete('github_token');
    }
}

export async function getGitHubUser(token: string): Promise<{ id: string; login: string } | null> {
    try {
        const res = await fetch('https://api.github.com/user', {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'application/json'
            }
        });
        const data = await res.json() as { id: number; login: string };
        return { id: String(data.id), login: data.login };
    } catch (err) {
        console.error('CodeSync: Failed to fetch GitHub user', err);
        return null;
    }
}