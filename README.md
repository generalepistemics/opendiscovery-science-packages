# Boltz for OpenDiscovery

Predict molecular structures, screen libraries and design binders through the Boltz API. Includes seven companion workflows and the maintained MCP server.

Install from Discover → Science → Boltz. Ask the agent to check Boltz setup, then explicitly approve installation of the official CLI if required and sign in with your Boltz account. Node.js is provided by the OpenDiscovery host; Boltz components and account access are separate requirements.

Estimate a workflow before starting it. Results download to the package’s private output directory. Copy requested artifacts into the selected project using the returned paths. Closing the app or removing this package does not cancel a remote Boltz job.

## Attribution

The MCP implementation includes code from boltz-bio/boltz-mcpb under the included MIT license. General Epistemics maintains the OpenDiscovery integration.

The supplied CLI-only ADME skill is not advertised because this MCP server exposes no matching ADME workflow.
