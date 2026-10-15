# Hosting profile

Use the static output of `principia-asd build-site`, not the Python development server.

See [public site and local companion](../docs/PUBLIC_SITE_AND_LOCAL_COMPANION.md) for the data-flow contract, visitor setup, build command, current publication gate and rollback instructions. `nginx.conf` is a template to validate on the eventual target server; no nginx deployment is performed locally.

The public site serves GET/HEAD only. Private discovery requires a companion running on each visitor's own computer, with their own private workspace and SiliconFlow key.
