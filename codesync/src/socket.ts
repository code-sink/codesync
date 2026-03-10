import WebSocket = require('ws');
import * as vscode from 'vscode';

const SERVER_URL = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000';

export class SocketClient {
    private ws: WebSocket | null = null;
    private jwt: string | null = null;
    private reconnectTimeout: NodeJS.Timeout | null = null;
    private currentRepo: { owner: string; repo: string; branch: string } | null = null;

    async connect(githubToken: string, repoOwner: string, repoName: string, branch: string): Promise<void> {
        this.currentRepo = { owner: repoOwner, repo: repoName, branch };

        // exchange github token for server jwt
        try {
            const res = await fetch(`${SERVER_URL}/auth/extension/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ github_token: githubToken })
            });
            const data = await res.json() as { access_token: string };
            this.jwt = data.access_token;
        } catch (err) {
            console.error('CodeSync: Failed to get JWT', err);
            vscode.window.showErrorMessage('CodeSync: Failed to authenticate with server');
            return;
        }

        this.openConnection();
    }

    private openConnection(): void {
        if (!this.jwt) return;

        this.ws = new WebSocket(`${WS_URL}/developer-updates?token=${this.jwt}`);

        this.ws.on('open', () => {
            console.log('CodeSync: WebSocket connected');
            vscode.window.showInformationMessage('CodeSync: Connected to server');
        });

        this.ws.on('message', (data: WebSocket.Data) => {
            try {
                const msg = JSON.parse(data.toString());
                this.handleMessage(msg);
            } catch (err) {
                console.error('CodeSync: Failed to parse message', err);
            }
        });

        this.ws.on('close', () => {
            console.log('CodeSync: WebSocket closed, attempting reconnect...');
            this.scheduleReconnect();
        });

        this.ws.on('error', (err) => {
            console.error('CodeSync: WebSocket error', err);
        });
    }

    private handleMessage(msg: any): void {
        // unsolicited message from server, to notify the user remote state has been moved forward
        if (msg.type === 'stale_notify') {
            vscode.window.showWarningMessage(
                `CodeSync: Your local version of ${msg.path} is outdated. Please pull from remote.`
            );
            return;
        }

        // responses to our messages
        if (!msg.ok) {
            console.error(`CodeSync: Server error [${msg.error}]: ${msg.detail}`);
            return;
        }

        switch (msg.type) {
            case 'patch_update':
                if (msg.conflict) {
                    vscode.window.showWarningMessage(
                        `CodeSync: Conflict detected — another developer has overlapping changes.`
                    );
                    console.log('Conflicting patches:', msg.conflicting_patches);
                }
                break;
            case 'branch_update':
                console.log('CodeSync: Branch update acknowledged by server');
                break;
            case 'base_commit_update':
                console.log('CodeSync: Base commit update acknowledged by server');
                break;
        }
    }

    sendPatchUpdate(
        devId: string,
        owner: string,
        repo: string,
        branch: string,
        filePath: string,
        baseCommit: string,
        patch: string,
        author?: string
    ): void {
        this.send({
            type: 'patch_update',
            dev_id: devId,
            owner,
            repo,
            branch,
            path: filePath,
            base_commit: baseCommit,
            patch,
            author,
            timestamp: Date.now() / 1000
        });
    }

    sendBranchUpdate(
        devId: string,
        owner: string,
        repo: string,
        oldBranch: string,
        newBranch: string,
        baseCommit: string,
        newBaseCommit?: string
    ): void {
        this.send({
            type: 'branch_update',
            dev_id: devId,
            owner,
            repo,
            old_branch: oldBranch,
            new_branch: newBranch,
            base_commit: baseCommit,
            new_base_commit: newBaseCommit
        });
    }

    sendBaseCommitUpdate(
        devId: string,
        owner: string,
        repo: string,
        branch: string,
        oldBase: string,
        newBase: string,
        operation: 'pull' | 'rebase'
    ): void {
        this.send({
            type: 'base_commit_update',
            dev_id: devId,
            owner,
            repo,
            branch,
            old_base: oldBase,
            new_base: newBase,
            operation
        });
    }

    private send(payload: object): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(payload));
        } else {
            console.warn('CodeSync: Attempted to send message but socket is not open');
        }
    }

    private scheduleReconnect(): void {
        this.reconnectTimeout = setTimeout(() => {
            console.log('CodeSync: Reconnecting...');
            this.openConnection();
        }, 5000);
    }

    dispose(): void {
        if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
        this.ws?.close();
    }
}