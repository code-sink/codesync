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