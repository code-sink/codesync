// authentication with github
import * as vscode from 'vscode';

export class AuthManager {
    constructor(private context: vscode.ExtensionContext) {}

    async getToken(): Promise<string | null> {
        const token = await this.context.secrets.get('github_token');
        return token ?? null;
    }

    async authenticate(): Promise<string | null> {
        // Use VS Code's built-in GitHub authentication
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