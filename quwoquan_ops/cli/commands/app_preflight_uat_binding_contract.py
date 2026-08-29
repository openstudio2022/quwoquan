"""Closed-set startup identity and build-seal fields for app-content UAT."""

from __future__ import annotations

import re

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
_BUILD_PROJECTION_SEAL_FIELDS = {
    "schema",
    "policyId",
    "sourceProjectionDigest",
    "sourceEntryCount",
    "derivedOutputDigest",
    "derivedOutputPolicyDigest",
    "derivedEntryCount",
    "buildProjectionDigest",
}
_APP_CONTENT_IMMUTABLE_STARTUP_IDENTITY_FIELDS = (
    "candidateDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "imageTransportTag",
)
# Legacy private import name retained only because stackctl re-exports it.  The
# value and both compatibility wrappers below are immutable-candidate-only.
_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS = (
    _APP_CONTENT_IMMUTABLE_STARTUP_IDENTITY_FIELDS
)
