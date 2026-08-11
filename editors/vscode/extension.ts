import * as path from 'path';
import { workspace, ExtensionContext } from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: ExtensionContext) {
  const serverPath = workspace.getConfiguration('vasp-lsp').get<string>('serverPath') || 'vasp-lsp';

  const serverOptions: ServerOptions = {
    command: serverPath,
    args: ['--stdio'],
    transport: TransportKind.stdio,
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: 'file', language: 'vasp-in' },
      { scheme: 'file', language: 'vasp-poscar' },
      { scheme: 'file', language: 'vasp-kpoints' },
      { scheme: 'file', language: 'vasp-potcar' },
      { scheme: 'file', language: 'vasp-log' },
    ],
    synchronize: {
      fileEvents: workspace.createFileSystemWatcher(
        '**/{INCAR,POSCAR,CONTCAR,KPOINTS,POTCAR}*'
      ),
    },
  };

  client = new LanguageClient(
    'vasp-lsp',
    'VASP Language Server',
    serverOptions,
    clientOptions
  );

  client.start();
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
