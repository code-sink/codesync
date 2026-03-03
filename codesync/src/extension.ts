// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import { AuthManager } from './auth';
import { FileWatcher } from './fileWatcher';
import { monitorGitRepository } from './git';

let statusBar: vscode.StatusBarItem; 

// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
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

    await monitorGitRepository(
		(repo) => {
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
            vscode.window.showInformationMessage(`CodeSync: Monitoring ${repo.remoteUrl}`);

            const watcher = new FileWatcher((event) => {
                console.log('FileEvent:', event);
            });
            context.subscriptions.push({ dispose: () => watcher.dispose() });
        },
        (repo) => {
            // branch changed or repo state updated
            statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
            console.log('Repo state changed:', repo);
        }
	);

	//statusBar.text = '$(git-branch) CodeSync: No GitHub repo detected';

	const mockCommand = vscode.commands.registerCommand('codesync.mockNotification', () => {
        vscode.window.showWarningMessage(
            'CodeSync: sarah is editing the same file as you (src/auth.ts, lines 12–34)'
        );
    });
    context.subscriptions.push(mockCommand);
}

// This method is called when your extension is deactivated
export function deactivate() {
	console.log('CodeSync deactivated');
}
