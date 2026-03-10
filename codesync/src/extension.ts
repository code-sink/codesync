import * as vscode from 'vscode';
import { AuthManager, getGitHubUser } from './auth';
import { FileWatcher } from './fileWatcher';
import { monitorGitRepository, getCurrentCommitHash, parseRemoteUrl, computeDiff } from './git';
import { SocketClient } from './socket';

const socketClient = new SocketClient();

let statusBar: vscode.StatusBarItem; 
let currentBranch: string | null = null; 
let baseCommitHash: string | undefined; 

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
    const devId = githubUser.id;
    console.log('Authentication complete'); 

    await monitorGitRepository(
		async (repo) => {
            currentBranch = repo.branch; 
            baseCommitHash = getCurrentCommitHash(); 
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
            vscode.window.showInformationMessage(`CodeSync: Monitoring ${repo.remoteUrl}`);
            
            const parsed = parseRemoteUrl(repo.remoteUrl); 
            if (!parsed) {
                vscode.window.showWarningMessage('CodeSync: Could not parse remote URL');
                return;
            }
            const { owner, repoName } = parsed; 

            await socketClient.connect(token, owner, repoName, repo.branch)
            const watcher = new FileWatcher(async (event) => {
                console.log('FileEvent:', {...event, baseCommitHash});

                if (event.type == 'save' && baseCommitHash) {
                    const patch = await computeDiff(event.filePath, repo.path);
                    if (patch) socketClient.sendPatchUpdate(
                        devId, 
                        parsed.owner, 
                        parsed.repoName, 
                        currentBranch!, 
                        event.filePath, 
                        baseCommitHash, 
                        patch
                    ); 
                }
            });
            context.subscriptions.push({ dispose: () => watcher.dispose() });
        },
        (repo) => {
            // branch changed or repo state updated
            const newCommitHash = getCurrentCommitHash(); 
        
            if (repo.branch != currentBranch) {
                // branch has changed, send branch_update to server
                currentBranch = repo.branch; 
                baseCommitHash = newCommitHash; 
                console.log('Branch switched, new commit hash: ', baseCommitHash); 
            } else if (newCommitHash != baseCommitHash) {
                // same branch but base commit hash has changed, send base_commit_update to server
                const oldHash = baseCommitHash; 
                baseCommitHash = newCommitHash; 
                console.log('Pull rebase detected, base commit advanced: ', oldHash, '->', baseCommitHash); 
            }
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
            console.log('Repo state changed:', repo);
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
