"""Test fixture — the actual captive-portal URL pair the user pasted in
the PortalLens design conversation. Used by tests that verify the
analyzer produces the expected inferences on real-world inputs."""

from __future__ import annotations

# The local captive hostname — a MikroTik hotspot that emits link-login,
# link-orig, dst, mac, ip, and the full MikroTik portal variable set.
MAZ_URL = (
    "http://maz.wifi/login?dst=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"
)

# The external ISPMan captive portal URL the local hotspot redirects to.
# Captured verbatim from the PortalLens design conversation — includes
# the operator/hotspot/session UUIDs in the path, the MikroTik-style
# query parameters (forwarded by the redirect), and the canvas/cookie
# fingerprint payloads the portal JavaScript collects.
ISPMAN_URL = (
    "https://captive.ispman.tech/hotspots/"
    "366ba450-bc93-4970-97d6-0585aa985a12/"
    "381168ce-bbb2-4f86-8fb8-d6d48321d8bb/"
    "4D415959205052495354/"
    "ispman-paid/select"
    "?mac=04%3AED%3A33%3A76%3AD9%3AA0"
    "&ip=10.111.151.194"
    "&username="
    "&link-login=http%3A%2F%2Fmaz.wifi%2Flogin%3Fdst%3Dhttp%253A%252F%252Fwww.msftconnecttest.com%252Fredirect"
    "&link-login-only=http%3A%2F%2Fmaz.wifi%2Flogin"
    "&link-orig=http%3A%2F%2Fwww.msftconnecttest.com%2Fredirect"
    "&error="
    "&height=652&width=1236"
    "&platform=Win32"
    "&timezone=Africa%2FNairobi"
    "&userAgent=Mozilla%2F5.0+%28Windows+NT+10.0%3B+Win64%3B+x64%29"
    "&webgl="
    "&canvasFingerprint=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAA"
    "&cookie="
)
