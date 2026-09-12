# Security policy

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is enabled for the repository. If it is unavailable, open a minimal issue asking for a private contact channel without including exploit details.

Do not paste credentials, private paths, personal photos, or session content into an issue or attachment.

## Scope notes

This is a local image-generation tool. It reads local images and writes local PNGs; it does not host services or store credentials. By default it does not transmit user photos. Two documented exceptions matter when assessing reports:

- The web tool loads a vendored copy of the matting model from `web/vendor/` (assets verified by SHA-256 against the upstream manifest); pinned public CDNs (esm.sh / jsDelivr / unpkg) are only a fallback. Photo data itself stays in the browser.
- The optional `engine/design_emblem.py` adapter uploads a compressed copy of the input photo to the user-configured vision-API endpoint (`OPENAI_BASE_URL`, default `api.openai.com`) together with the API key from the environment. Plaintext `http://` endpoints are rejected except for loopback addresses.

Reports are expected to concern local processing, dependency versions, or documentation.
