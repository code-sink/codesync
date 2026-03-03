/******/ (() => { // webpackBootstrap
/******/ 	"use strict";
/******/ 	var __webpack_modules__ = ([
/* 0 */
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.activate = activate;
exports.deactivate = deactivate;
// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
const vscode = __importStar(__webpack_require__(1));
const auth_1 = __webpack_require__(2);
const fileWatcher_1 = __webpack_require__(3);
const git_1 = __webpack_require__(4);
let statusBar;
// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
async function activate(context) {
    console.log('CodeSync: activate() called');
    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
    statusBar.text = '$(git-branch) CodeSync: Starting...';
    statusBar.show();
    context.subscriptions.push(statusBar);
    const auth = new auth_1.AuthManager(context);
    const token = await auth.authenticate();
    if (!token) {
        statusBar.text = '$(error) CodeSync: Auth failed';
        vscode.window.showWarningMessage('CodeSync: GitHub auth failed');
        return;
    }
    await (0, git_1.monitorGitRepository)((repo) => {
        statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
        vscode.window.showInformationMessage(`CodeSync: Monitoring ${repo.remoteUrl}`);
        const watcher = new fileWatcher_1.FileWatcher((event) => {
            console.log('FileEvent:', event);
        });
        context.subscriptions.push({ dispose: () => watcher.dispose() });
    }, (repo) => {
        // branch changed or repo state updated
        statusBar.text = `$(git-branch) CodeSync: ${repo.branch}`;
        console.log('Repo state changed:', repo);
    });
    //statusBar.text = '$(git-branch) CodeSync: No GitHub repo detected';
    const mockCommand = vscode.commands.registerCommand('codesync.mockNotification', () => {
        vscode.window.showWarningMessage('CodeSync: sarah is editing the same file as you (src/auth.ts, lines 12–34)');
    });
    context.subscriptions.push(mockCommand);
}
// This method is called when your extension is deactivated
function deactivate() {
    console.log('CodeSync deactivated');
}


/***/ }),
/* 1 */
/***/ ((module) => {

module.exports = require("vscode");

/***/ }),
/* 2 */
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.AuthManager = void 0;
// authentication with github
const vscode = __importStar(__webpack_require__(1));
class AuthManager {
    context;
    constructor(context) {
        this.context = context;
    }
    async getToken() {
        const token = await this.context.secrets.get('github_token');
        return token ?? null;
    }
    async authenticate() {
        // Use VS Code's built-in GitHub authentication
        const session = await vscode.authentication.getSession('github', ['repo', 'user:email'], { createIfNone: true });
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
exports.AuthManager = AuthManager;


/***/ }),
/* 3 */
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.FileWatcher = void 0;
// this file will watch local file changes
const vscode = __importStar(__webpack_require__(1));
class FileWatcher {
    onFileChange;
    debounceTimers = new Map();
    constructor(onFileChange) {
        this.onFileChange = onFileChange;
        this.setupWatchers();
    }
    setupWatchers() {
        // to detect a file being edited
        vscode.workspace.onDidChangeTextDocument((e) => {
            const filePath = vscode.workspace.asRelativePath(e.document.uri);
            if (this.shouldIgnore(filePath))
                return;
            // to extract changed lines
            const linesChanged = new Set();
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
    pendingLines = new Map();
    debounceEdit(filePath, linesChanged) {
        if (!this.pendingLines.has(filePath)) {
            this.pendingLines.set(filePath, new Set());
        }
        linesChanged.forEach(l => this.pendingLines.get(filePath).add(l));
        const existingTimer = this.debounceTimers.get(filePath);
        if (existingTimer)
            clearTimeout(existingTimer);
        const timer = setTimeout(() => {
            const lines = Array.from(this.pendingLines.get(filePath) || []);
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
    shouldIgnore(filePath) {
        const ignored = ['node_modules/', '.git/', 'dist/', '.env'];
        return ignored.some(pattern => filePath.includes(pattern));
    }
    dispose() {
        this.debounceTimers.forEach(timer => clearTimeout(timer));
    }
}
exports.FileWatcher = FileWatcher;


/***/ }),
/* 4 */
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.monitorGitRepository = monitorGitRepository;
// this file will be used for git detection
const vscode = __importStar(__webpack_require__(1));
async function monitorGitRepository(onRepoDetected, onRepoChanged) {
    const gitExtension = vscode.extensions.getExtension('vscode.git');
    if (!gitExtension)
        return;
    await gitExtension.activate();
    const git = gitExtension.exports.getAPI(1);
    const extractRepoInfo = (repo) => {
        const remotes = repo.state.remotes;
        const remoteUrl = remotes.length > 0 ? remotes[0].fetchUrl : null;
        if (!remoteUrl || !remoteUrl.includes('github.com'))
            return null;
        return {
            path: repo.rootUri.fsPath,
            remoteUrl,
            branch: repo.state.HEAD?.name || 'unknown'
        };
    };
    // handle repos already open when extension activates
    if (git.repositories.length > 0) {
        const info = extractRepoInfo(git.repositories[0]);
        if (info)
            onRepoDetected(info);
    }
    // handle repos opened after activation, or branch/HEAD changes
    git.repositories.forEach((repo) => {
        repo.state.onDidChange(() => {
            const info = extractRepoInfo(repo);
            if (info)
                onRepoChanged(info);
        });
    });
    // handle a repo being added to the workspace mid-session
    git.onDidOpenRepository((repo) => {
        const info = extractRepoInfo(repo);
        if (info)
            onRepoDetected(info);
        repo.state.onDidChange(() => {
            const info = extractRepoInfo(repo);
            if (info)
                onRepoChanged(info);
        });
    });
}


/***/ })
/******/ 	]);
/************************************************************************/
/******/ 	// The module cache
/******/ 	var __webpack_module_cache__ = {};
/******/ 	
/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {
/******/ 		// Check if module is in cache
/******/ 		var cachedModule = __webpack_module_cache__[moduleId];
/******/ 		if (cachedModule !== undefined) {
/******/ 			return cachedModule.exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = __webpack_module_cache__[moduleId] = {
/******/ 			// no module.id needed
/******/ 			// no module.loaded needed
/******/ 			exports: {}
/******/ 		};
/******/ 	
/******/ 		// Execute the module function
/******/ 		__webpack_modules__[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/ 	
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/ 	
/************************************************************************/
/******/ 	
/******/ 	// startup
/******/ 	// Load entry module and return exports
/******/ 	// This entry module is referenced by other modules so it can't be inlined
/******/ 	var __webpack_exports__ = __webpack_require__(0);
/******/ 	module.exports = __webpack_exports__;
/******/ 	
/******/ })()
;
//# sourceMappingURL=extension.js.map