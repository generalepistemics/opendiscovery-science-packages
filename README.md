# OpenDiscovery Science Packages

Optional scientific workflows and service packages for OpenDiscovery.

| Package | Includes | Installation source |
| --- | --- | --- |
| Life Sciences Databases | 44 database skills, scripts, and source references | `https://github.com/generalepistemics/opendiscovery-science-packages#life-sciences-databases` |
| Scientific Research | Nine research and writing workflows | `https://github.com/generalepistemics/opendiscovery-science-packages#scientific-research` |
| Adaptyv Workflows | Four workflows for preparing and tracking experiments | `https://github.com/generalepistemics/opendiscovery-science-packages#adaptyv-workflows` |
| Boltz | MCP server and seven molecular prediction/design workflows | `https://github.com/generalepistemics/opendiscovery-science-packages#boltz` |

## Install

Open **Discover → Science** in a compatible OpenDiscovery release. Select a package, review its contents, and install it. Complete any required activation, runtime setup, or provider sign-in before using its workflows.

For manual installation, open **Settings → Extensions → Apps** and paste the package's installation source above. Each named branch contains a prepared package at its root. The repository's default branch is an index, not an installable package.

Life Sciences Databases requires Python 3.10 or newer on the engine host and includes its shared HTTP dependencies. Scientific Research's optional numerical scripts and manuscript compilation have additional documented requirements. Boltz requires separate CLI setup and account access. Adaptyv Workflows requires a configured Adaptyv MCP connection.

## Updates and removal

Use OpenDiscovery's package update action. Packages are versioned independently of the application. Updates that expand requested capabilities require review. Disable or remove a package to withdraw its contributions; project files and remote provider jobs remain separate.

## Package contents

Each package branch includes its manifest, runtime resources, documentation, applicable notices, and `checksums.json`. Dependencies needed at runtime are included where documented; installation does not run a source build.

Third-party service names identify their respective operators. Provider subscriptions, credits, credentials, and data access are not included.
