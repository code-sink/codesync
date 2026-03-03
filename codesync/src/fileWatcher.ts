// this file will watch local file changes
import * as vscode from 'vscode';

export interface FileChangeEvent {
    type: 'open' | 'edit' | 'save' | 'close';
    filePath: string;
    linesChanged?: number[];
    timestamp: string;
}

export class FileWatcher {
    private onFileChange: (event: FileChangeEvent) => void;
    private debounceTimers = new Map<string, NodeJS.Timeout>();

    constructor(onFileChange: (event: FileChangeEvent) => void) {
        this.onFileChange = onFileChange;
        this.setupWatchers();
    }

    private setupWatchers() {
        // to detect a file being edited
        vscode.workspace.onDidChangeTextDocument((e) => {
            const filePath = vscode.workspace.asRelativePath(e.document.uri);
            
            if (this.shouldIgnore(filePath)) return;

            // to extract changed lines
            const linesChanged = new Set<number>();
            e.contentChanges.forEach(change => {
                for (let i = change.range.start.line; i <= change.range.end.line; i++) {
                    linesChanged.add(i);
                }
            });

            this.debounceEdit(filePath, Array.from(linesChanged));
        });

        // to detect a file being saved
        vscode.workspace.onDidSaveTextDocument((doc) => {
            const filePath = vscode.workspace.asRelativePath(doc.uri);
            if (!this.shouldIgnore(filePath)) {
                this.onFileChange({ type: 'save', filePath, timestamp: new Date().toISOString() });
            }
        });
        
        // to detect a file being closed
        vscode.workspace.onDidCloseTextDocument((doc) => {
            const filePath = vscode.workspace.asRelativePath(doc.uri);
            if (!this.shouldIgnore(filePath)) {
                this.onFileChange({ type: 'close', filePath, timestamp: new Date().toISOString() });
            }
        });

        // to detect a file being opened
        vscode.window.onDidChangeActiveTextEditor((editor) => {
            if (editor) {
                const filePath = vscode.workspace.asRelativePath(editor.document.uri);
                if (!this.shouldIgnore(filePath)) {
                    this.onFileChange({
                        type: 'open',
                        filePath,
                        timestamp: new Date().toISOString()
                    });
                }
            }
        });
    }

    private pendingLines = new Map<string, Set<number>>();

    private debounceEdit(filePath: string, linesChanged: number[]) {
        if (!this.pendingLines.has(filePath)) {
            this.pendingLines.set(filePath, new Set());
        }
        linesChanged.forEach(l => this.pendingLines.get(filePath)!.add(l));

        const existingTimer = this.debounceTimers.get(filePath);
        if (existingTimer) clearTimeout(existingTimer);

        const timer = setTimeout(() => {
            const lines = Array.from(this.pendingLines.get(filePath) || [])
            this.onFileChange({
                type: 'edit',
                filePath,
                linesChanged,
                timestamp: new Date().toISOString()
            });
            this.debounceTimers.delete(filePath);
            this.pendingLines.delete(filePath);
        }, 2000); // 2 second debounce

        this.debounceTimers.set(filePath, timer);
    }

    private shouldIgnore(filePath: string): boolean {
        const ignored = ['node_modules/', '.git/', 'dist/', '.env'];
        return ignored.some(pattern => filePath.includes(pattern));
    }

    dispose() {
        this.debounceTimers.forEach(timer => clearTimeout(timer));
    }
}