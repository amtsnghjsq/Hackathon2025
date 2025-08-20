import * as vscode from 'vscode';
import * as fs from 'fs';

type ChatMessage = { role: 'system' | 'user' | 'assistant'; content: string };

export class ChatPanel {
	public static currentPanel: ChatPanel | undefined;

	private readonly panel: vscode.WebviewPanel;
	private readonly extensionUri: vscode.Uri;
	private disposables: vscode.Disposable[] = [];
	private conversation: ChatMessage[] = [
		{ role: 'system', content: 'You are a helpful onboarding assistant inside VS Code. Be concise and helpful.' }
	];
	private sessionId: string = generateSessionId();
	private currentAbortController: AbortController | null = null;

	public static createOrShow(context: vscode.ExtensionContext) {
		const column = vscode.window.activeTextEditor ? vscode.window.activeTextEditor.viewColumn : undefined;
		// If we already have a panel, show it.
		if (ChatPanel.currentPanel) {
			ChatPanel.currentPanel.panel.reveal(column);
			return;
		}

		// Otherwise, create a new panel.
		const panel = vscode.window.createWebviewPanel(
			'chatbotAssistant',
			'JSQ buddy',
			column ?? vscode.ViewColumn.Beside,
			{
				enableScripts: true,
				retainContextWhenHidden: true,
				localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')]
			}
		);

		ChatPanel.currentPanel = new ChatPanel(panel, context.extensionUri);
	}

	private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
		this.panel = panel;
		this.extensionUri = extensionUri;
		this.panel.iconPath = vscode.Uri.joinPath(this.extensionUri, 'media', 'jsqlogo.png');
		this.panel.webview.html = this.getHtmlForWebview(this.panel.webview);

		this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

		this.panel.webview.onDidReceiveMessage(async (message) => {
			switch (message.type) {
				case 'sendMessage': {
					const userText = String(message.text ?? '').trim();
					if (!userText) {
						return;
					}
					this.handleUserMessage(userText).catch((err) => {
						this.postError(err instanceof Error ? err.message : String(err));
					});
					break;
				}
				case 'cancel': {
					this.currentAbortController?.abort();
					break;
				}
				case 'newChat': {
					this.resetConversation();
					break;
				}
				default:
					break;
			}
		}, undefined, this.disposables);
	}

	public dispose() {
		ChatPanel.currentPanel = undefined;
		while (this.disposables.length) {
			const x = this.disposables.pop();
			if (x) {
				x.dispose();
			}
		}
	}

	private getHtmlForWebview(webview: vscode.Webview): string {
		const mediaPath = vscode.Uri.joinPath(this.extensionUri, 'media');
		const htmlPath = vscode.Uri.joinPath(mediaPath, 'chat.html');
		let html = '';
		try {
			html = fs.readFileSync(htmlPath.fsPath, 'utf8');
		} catch (e) {
			html = '<!DOCTYPE html><html><body><h3>ChatBot Assistant</h3><p>Missing media/chat.html</p></body></html>';
		}

		const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'chat.js'));
		const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'chat.css'));
		const logoUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'jsqlogo.png'));
		const animUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'Loading animation.json'));
		const assistAnimUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'assistant response.json'));
		const nonce = getNonce();

		// Replace placeholders in HTML template
		html = html
			.replace(/%SCRIPT_URI%/g, String(scriptUri))
			.replace(/%STYLE_URI%/g, String(styleUri))
			.replace(/%LOGO_URI%/g, String(logoUri))
			.replace(/%ANIM_URI%/g, String(animUri))
			.replace(/%ASSIST_ANIM_URI%/g, String(assistAnimUri))
			.replace(/%CSP_SOURCE%/g, webview.cspSource)
			.replace(/%NONCE%/g, nonce);

		return html;
	}

	private async handleUserMessage(userText: string) {
		// Push user message to conversation
		this.conversation.push({ role: 'user', content: userText });
		this.panel.webview.postMessage({ type: 'userMessage', text: userText });

		// Cancel any ongoing request
		this.currentAbortController?.abort();
		const abortController = new AbortController();
		this.currentAbortController = abortController;

		this.panel.webview.postMessage({ type: 'assistantStart' });

		try {
			let collected = '';
			await this.streamFromLocalServer(this.conversation, (delta) => {
				if (abortController.signal.aborted) {
					return;
				}
				collected += delta;
				this.panel.webview.postMessage({ type: 'appendResponse', delta });
			}, abortController.signal);
			// Store assistant message
			this.conversation.push({ role: 'assistant', content: collected });
			this.panel.webview.postMessage({ type: 'assistantComplete' });
		} catch (err) {
			if ((err as any)?.name === 'AbortError') {
				this.panel.webview.postMessage({ type: 'status', text: 'Cancelled.' });
				return;
			}
			this.postError(err instanceof Error ? err.message : String(err));
		} finally {
			if (this.currentAbortController === abortController) {
				this.currentAbortController = null;
			}
		}
	}

	private postError(message: string) {
		this.panel.webview.postMessage({ type: 'error', message });
	}

	private resetConversation() {
		this.currentAbortController?.abort();
		this.conversation = [
			{ role: 'system', content: 'You are a helpful onboarding assistant inside VS Code. Be concise and helpful.' }
		];
		this.sessionId = generateSessionId();
		this.panel.webview.postMessage({ type: 'reset', sessionId: this.sessionId });
	}

	private async streamFromLocalServer(
		messages: ChatMessage[],
		onDelta: (delta: string) => void,
		signal: AbortSignal
	): Promise<void> {
		const url = 'http://127.0.0.1:7800/v1/chat/stream';
		const headers = { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' };
		// For Bedrock agent runtime, we forward only the latest user prompt; server keeps session
		const lastUser = [...messages].reverse().find((m) => m.role === 'user');
		const body = JSON.stringify({ prompt: lastUser?.content || '', sessionId: this.sessionId });

		let response: Response;
		try {
			response = await fetch(url, { method: 'POST', headers, body, signal });
		} catch (e) {
			throw new Error('Could not reach local Gemini server. Is it running?');
		}
		if (!response.ok || !response.body) {
			let details = '';
			try { const j: any = await response.json(); details = j?.error || JSON.stringify(j); } catch {}
			throw new Error(`Local server error (${response.status}). ${details}`.trim());
		}

		const reader = response.body.getReader();
		const decoder = new TextDecoder('utf-8');
		let buffer = '';
		while (true) {
			const { value, done } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			// process per-line for minimal latency
			const parts = buffer.split(/\n\n/);
			buffer = parts.pop() ?? '';
			for (const part of parts) {
				const lines = part.split('\n');
				for (const line of lines) {
					const trimmed = line.trim();
					if (!trimmed.startsWith('data:')) continue;
					const data = trimmed.slice(5).trim();
					if (data === '[DONE]') return;
					try {
						const json = JSON.parse(data);
						if (typeof json?.text === 'string' && json.text.length > 0) {
							onDelta(json.text);
						}
					} catch {}
				}
			}
		}
	}
}

function getNonce() {
	let text = '';
	const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	for (let i = 0; i < 32; i++) {
		text += possible.charAt(Math.floor(Math.random() * possible.length));
	}
	return text;
}

function generateSessionId(): string {
	return 'chat-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}


