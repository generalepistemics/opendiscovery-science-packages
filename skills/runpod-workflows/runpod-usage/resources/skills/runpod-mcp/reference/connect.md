# Connect Runpod

Install Runpod in OpenDiscovery Discover, then authenticate through Settings → Extensions → MCP servers. The hosted URL is `https://mcp.runpod.io/`. Existing manual MCP configurations must be preserved.

OAuth authenticates MCP calls. Local runpodctl/Flash workflows need their separately configured `RUNPOD_API_KEY`. For explicitly requested API-key MCP access, use the masked credentials/header settings and current provider documentation; never interpolate a secret into a shell command, log or message.

A user who chooses a local stdio server may configure `npx -y @runpod/mcp-server` through the existing MCP command form with the required environment. This is an alternative deployment, not a second mandatory installation. Check the installed version and live schema. Do not use another agent's configuration CLI.
