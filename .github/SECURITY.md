# Security

The current 1.0.x release line receives security fixes as they become available.

For a vulnerability, please use
[GitHub's private vulnerability reporting](https://github.com/tsuikaii/Audio_Forge/security/advisories/new).
Include the affected version, reproduction steps, and expected impact. Do not
post personal media or credentials. Response times depend on maintainer
availability; this small project has no guaranteed response SLA.

The native client serves its UI on a random `127.0.0.1` port. It checks the host,
origin, and per-launch authentication token. The UI loads no remote resources.
The application processes files locally and does not provide a remote service.
The release includes FFmpeg and Python: malformed media or a compromised build
dependency can still affect the local application. Use a maintained release.
