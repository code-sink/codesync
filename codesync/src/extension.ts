import * as vscode from 'vscode';
import { AuthManager, getGitHubUser } from './auth';
import { FileWatcher } from './fileWatcher';
import { monitorGitRepository, getCurrentCommitHash, parseRemoteUrl, computeDiff, getModifiedFiles } from './git';
import { SocketClient } from './socket';

const socketClient = new SocketClient();

let statusBar: vscode.StatusBarItem;
let currentBranch: string | null = null;
let baseCommitHash: string | undefined;
let devId: string;
let owner: string;
let repoName: string;
let oldHash: string | undefined;

export async function activate(context: vscode.ExtensionContext) {
    console.log('CodeSync: activate() called');

    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
    statusBar.text = '$(git-branch) CodeSync: Starting...';
    statusBar.show();
    context.subscriptions.push(statusBar);

    const auth = new AuthManager(context);
    const token = await auth.authenticate();
    if (!token) {
        statusBar.text = '$(error) CodeSync: Auth failed';
        vscode.window.showWarningMessage('CodeSync: GitHub auth failed');
        return;
    }
    const githubUser = await getGitHubUser(token);
    if (!githubUser) {
        vscode.window.showWarningMessage('CodeSync: Failed to fetch GitHub user info');
        return;
    }
    devId = githubUser.id;
    console.log('Authentication complete');

    async function syncRepositoryState(repoPath: string, owner: string, repo: string, branch: string, hash: string) {
        const modifiedFiles = await getModifiedFiles(repoPath);
        if (modifiedFiles.length > 0) {
            console.log(`DEBUG: syncRepositoryState starting. Found ${modifiedFiles.length} modified files.`);
            for (const filePath of modifiedFiles) {
                const patch = await computeDiff(filePath, repoPath);
                if (patch) {
                    console.log(`DEBUG: Sending patch for ${filePath} on branch ${branch}`);
                    socketClient.sendPatchUpdate(
                        devId,
                        owner,
                        repo,
                        branch,
                        filePath,
                        hash,
                        patch
                    );
                }
            }
        } else {
            console.log('DEBUG: syncRepositoryState skipped - no modified files found.');
        }
    }

    await monitorGitRepository(
        async (repo) => {
            // Initial setup for the detected repository
            baseCommitHash = getCurrentCommitHash();
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
            vscode.window.showInformationMessage(`CodeSync: Monitoring ${repo.remoteUrl}`);

            const parsed = parseRemoteUrl(repo.remoteUrl);
            if (!parsed) {
                vscode.window.showWarningMessage('CodeSync: Could not parse remote URL');
                return;
            }
            owner = parsed.owner;
            repoName = parsed.repoName;
            currentBranch = repo.branch;

            await socketClient.connect(token, owner, repoName, repo.branch)
            
            // Send initial branch update to register with backend
            console.log('DEBUG: Sending initial branch_update for', owner, '/', repoName);
            socketClient.sendBranchUpdate(
                devId,
                owner,
                repoName,
                '', // removed old branch arg
                repo.branch,
                '', // removed old hash arg
                baseCommitHash
            );

            // Initial re-sync
            if (baseCommitHash) {
                await syncRepositoryState(repo.path, owner, repoName, repo.branch, baseCommitHash);
            }

            const watcher = new FileWatcher(async (event) => {
                console.log('DEBUG: FileWatcher event:', event.type, 'Path:', event.filePath, 'BaseHash:', baseCommitHash);

                if (event.type === 'save') {
                    // On save, re-sync the entire repo state to ensure accuracy
                    if (baseCommitHash) {
                        await syncRepositoryState(repo.path, owner, repoName, currentBranch!, baseCommitHash);
                    }
                } else if (event.type === 'edit') {
                    // On edit (keystroke), just send the single file patch for real-time updates
                    if (!baseCommitHash) {
                        console.warn('DEBUG: Skipping edit update - baseCommitHash is missing');
                        return;
                    }
                    const patch = await computeDiff(event.filePath, repo.path);
                    if (patch) {
                        console.log('DEBUG: Calling sendPatchUpdate (edit) for', event.filePath);
                        socketClient.sendPatchUpdate(
                            devId,
                            owner,
                            repoName,
                            currentBranch!,
                            event.filePath,
                            baseCommitHash,
                            patch
                        );
                    }
                }
            });
            context.subscriptions.push({ dispose: () => watcher.dispose() });
        },
        async (repo) => {
            console.log('DEBUG: onRepoChanged called. Branch:', repo.branch, 'Current:', currentBranch);
            const newCommitHash = getCurrentCommitHash();

            if (repo.branch != currentBranch) {
                console.log('DEBUG: Branch switch detected:', currentBranch, '->', repo.branch);
                const oldBranch = currentBranch;
                oldHash = baseCommitHash;
                currentBranch = repo.branch;
                baseCommitHash = newCommitHash;

                const parsed = parseRemoteUrl(repo.remoteUrl);
                if (!parsed) {
                    console.error('DEBUG: Cannot send branch_update - Could not parse remote URL');
                    return;
                }

                console.log('DEBUG: Sending branch_update for', parsed.owner, '/', parsed.repoName);
                socketClient.sendBranchUpdate(
                    devId,
                    parsed.owner,
                    parsed.repoName,
                    oldBranch || '',
                    repo.branch,
                    oldHash || '',
                    newCommitHash
                );

                // Re-sync all modified files on the new branch
                if (newCommitHash) {
                    await syncRepositoryState(repo.path, parsed.owner, parsed.repoName, repo.branch, newCommitHash);
                }
            } else if (newCommitHash && newCommitHash != baseCommitHash) {
                console.log('DEBUG: Base commit change detected:', baseCommitHash, '->', newCommitHash);

                const parsed = parseRemoteUrl(repo.remoteUrl);
                if (parsed) {
                    // Inform backend about the base commit update
                    socketClient.sendBranchUpdate(
                        devId,
                        parsed.owner,
                        parsed.repoName,
                        repo.branch, // old and new are the same
                        repo.branch,
                        baseCommitHash || '',
                        newCommitHash
                    );

                    baseCommitHash = newCommitHash;

                    // Immediately re-sync to avoid the "dead zone"
                    await syncRepositoryState(repo.path, parsed.owner, parsed.repoName, repo.branch, newCommitHash);
                }
            }
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
        }
    );

    /* -------- mock commands for dev testing . will remove later ------- */

    const mockCommand = vscode.commands.registerCommand('codesync.mockNotification', () => {
        vscode.window.showWarningMessage(
            'CodeSync: sarah is editing the same file as you (src/auth.ts, lines 12–34)'
        );
    });
    context.subscriptions.push(mockCommand);

    const testWSCommand = vscode.commands.registerCommand('codesync.testPatch', async () => {
        socketClient.sendPatchUpdate(
            'test_user',
            'owner',
            'repo',
            'main',
            'src/test.ts',
            baseCommitHash || 'abc123',
            '--- a/src/test.ts\n+++ b/src/test.ts\n@@ -1,3 +1,4 @@\n line1\n+new line\n line2\n line3'
        );
        vscode.window.showInformationMessage('CodeSync: Test patch sent');
    });
    context.subscriptions.push(testWSCommand);
}

export function deactivate() {
    console.log('CodeSync deactivated');
}
