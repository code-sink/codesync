// this file will be used for git detection
import * as vscode from 'vscode';

export interface RepoInfo {
    path: string;
    remoteUrl: string;
    branch: string;
}

export async function monitorGitRepository(
    onRepoDetected: (repo: RepoInfo) => void,
    onRepoChanged: (repo: RepoInfo) => void
): Promise<void> {
    const gitExtension = vscode.extensions.getExtension('vscode.git');
    if (!gitExtension) return;

    await gitExtension.activate();
    const git = gitExtension.exports.getAPI(1);

    const extractRepoInfo = (repo: any): RepoInfo | null => {
        const remotes = repo.state.remotes;
        const remoteUrl = remotes.length > 0 ? remotes[0].fetchUrl : null;
        if (!remoteUrl || !remoteUrl.includes('github.com')) return null;

        return {
            path: repo.rootUri.fsPath,
            remoteUrl,
            branch: repo.state.HEAD?.name || 'unknown'
        };
    };

    // handle repos already open when extension activates
    if (git.repositories.length > 0) {
        const info = extractRepoInfo(git.repositories[0]);
        if (info) onRepoDetected(info);
    }

    // handle repos opened after activation, or branch/HEAD changes
    git.repositories.forEach((repo: any) => {
        /* repo.state.onDidChange is a listener that will trigger anytime a repo's state changes
         this includes a branch switch, or a base commit hash change (so user has done git pull --rebase)
         */
        repo.state.onDidChange(() => {
            const info = extractRepoInfo(repo);
            if (info) onRepoChanged(info);
        });
    });

    // handle a repo being added to the workspace mid-session
    git.onDidOpenRepository((repo: any) => {
        const info = extractRepoInfo(repo);
        if (info) onRepoDetected(info);

        repo.state.onDidChange(() => {
            const info = extractRepoInfo(repo);
            if (info) onRepoChanged(info);
        });
    });
}

export function getCurrentCommitHash(): string | undefined {
    const gitExtension = vscode.extensions.getExtension('vscode.git');
    if (!gitExtension) return;
    const git = gitExtension?.exports.getAPI(1); 
    return git?.repositories[0]?.state.HEAD?.commit; 
}

export function parseRemoteUrl(remoteUrl: string): { owner: string; repoName: string } | null {
    try {
        // to handle both https://github.com/owner/repo and git@github.com:owner/repo.git
        const httpsMatch = remoteUrl.match(/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?$/);
        const sshMatch = remoteUrl.match(/github\.com:([^/]+)\/([^/]+?)(?:\.git)?$/);

        const match = httpsMatch || sshMatch;
        if (!match) return null;

        return {
            owner: match[1],
            repoName: match[2]
        };
    } catch {
        return null;
    }
}

export async function computeDiff(
    filePath: string,
    repoPath: string
): Promise<string | null> {
    try {
        const gitExtension = vscode.extensions.getExtension('vscode.git');
        if (!gitExtension) return null;

        const git = gitExtension.exports.getAPI(1);
        if (!git?.repositories?.[0]) return null;

        const repo = git.repositories.find((r: any) => r.rootUri.fsPath === repoPath);
        if (!repo) return null;

        const absolutePath = vscode.Uri.file(`${repoPath}/${filePath}`);
        const diff = await repo.diffWithHEAD(absolutePath.fsPath);
        
        return diff || null;
    } catch (err) {
        console.error('CodeSync: Failed to compute diff', err);
        return null;
    }
}