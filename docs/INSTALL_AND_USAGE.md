# Clike — Install & Usage (MVP)

## Services
```bash
cd docker
docker compose up -d --build
# check
curl -s http://localhost:8080/health
curl -s http://localhost:8000/health
```

## VS Code Extension
- Already includes compiled entrypoint at `out/extension.js`.
```bash
cd extensions/vscode
npm i
npm i -g @vscode/vsce
vsce package
code --install-extension clike-0.0.1.vsix
```
