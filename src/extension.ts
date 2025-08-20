import * as vscode from 'vscode';
import { ChatPanel } from './panel';

export function activate(context: vscode.ExtensionContext) {
	const disposable = vscode.commands.registerCommand('chatbotAssistant.open', async () => {
		ChatPanel.createOrShow(context);
	});

	context.subscriptions.push(disposable);
}

export function deactivate() {}


