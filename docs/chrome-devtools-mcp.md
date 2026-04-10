# Chrome DevTools MCP

## Purpose
Use Chrome DevTools MCP with this repo for:
- Verifying the React UI on the Vite dev server
- Inspecting failed network requests from frontend to Flask
- Checking rendered state for trade, quote, watchlist, and filter flows

This repo does not auto-install or auto-enable the MCP. Activation is a local Codex/MCP configuration step on the machine running Codex.

## Typical workflow for this project
1. Start the backend: `cd backend && python3 server.py`
2. Start the frontend: `cd frontend && npm run dev`
3. Connect Chrome DevTools MCP from your local Codex/MCP setup
4. Open the Vite app and inspect:
   - quote lookups
   - buy/sell requests
   - watchlist create/update/delete flows
   - filter requests and error responses

## Recommended usage
- Use the Network panel to confirm request payloads and response status codes.
- Use Elements/Console to verify rendered state after user interactions.
- Use it for manual verification after backend validation passes, not as a replacement for lint/build/syntax checks.

## Local MCP config
Use the example in `docs/examples/chrome-devtools-mcp.example.json` as a template for your local Codex MCP configuration.

You will still need to adapt the command/path to match your local environment and the MCP package you have installed.

## Notes
- Keep Chrome DevTools MCP configuration local rather than committing machine-specific absolute paths into the repo.
- If you later standardize a team-wide MCP install path, update this doc and keep the committed file as a template, not a machine binding.
