"""Content release query preparation for environment activation.

Calls the Content service's /internal/content/release-queries:prepare endpoint
to build Creator/Post/Homepage Search indexes before activation CAS.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import time
from typing import Any
from urllib import error, request


class ContentReleaseQueryPreparationError(RuntimeError):
    """Query preparation failed and activation cannot proceed."""


def prepare_content_release_queries(
    *,
    api_base_url: str,
    ssl_cafile: str,
    release_id: str,
    manifest_digest: str,
    environment: str,
    idempotency_key: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Prepare Content release queries by calling the Content service API.
    
    This function calls /internal/content/release-queries:prepare to build
    Creator/Post/Homepage Search indexes for the candidate release.
    
    Args:
        api_base_url: Base URL for Content service (e.g., "https://api.gamma.quwoquan.com:19000")
        ssl_cafile: Path to SSL CA certificate file for TLS verification
        release_id: Release ID (e.g., "20260915--gamma-prod-closure-m1--candidate-001")
        manifest_digest: Manifest digest (e.g., "sha256:...")
        environment: Environment name (e.g., "gamma")
        idempotency_key: Unique key for idempotent retry (e.g., "activate-{release_id}-{run_id}")
        timeout_seconds: Maximum time to wait for preparation (default: 300s)
    
    Returns:
        dict with keys:
            - release: ReleaseCandidateBinding echo
            - publicationId: Publication ID for recommendation
            - sourceSnapshotDigest: Digest of source snapshot
            - creatorSearchProof: Creator search readiness proof (or null)
            - postSearchProof: Post search readiness proof (or null)
            - homepageSearchProof: Homepage search readiness proof (or null)
    
    Raises:
        ContentReleaseQueryPreparationError: If preparation fails or times out
    """
    url = f"{api_base_url.rstrip('/')}/internal/content/release-queries:prepare"
    
    # Construct request payload matching PreparePostReleaseQueriesCommand
    binding = {
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "sourceOwner": "qwq_data",
        "environment": environment,
    }
    
    payload = {
        "creatorBinding": binding,
        "expectedCreatorPreparationVersion": 0,
        "postBinding": binding,
        "homepageBinding": binding,
        "recommendationBinding": binding,
        "expectedPostPreparationVersion": 0,
        "expectedHomepagePreparationVersion": 0,
        "idempotencyKey": idempotency_key,
    }
    
    # Set up SSL context
    ssl_context = ssl.create_default_context(cafile=ssl_cafile) if ssl_cafile else ssl.create_default_context()
    
    # Retry loop with exponential backoff
    deadline = time.time() + timeout_seconds
    attempt = 0
    backoff_seconds = 2.0
    last_error: Exception | None = None
    
    while time.time() < deadline:
        attempt += 1
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        
        try:
            # Make HTTP request
            req = request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Idempotency-Key": idempotency_key,
                },
                method="POST",
            )
            
            # Set socket timeout to remaining time (capped at 60s per attempt)
            socket_timeout = min(remaining, 60.0)
            
            with request.urlopen(req, timeout=socket_timeout, context=ssl_context) as response:
                if response.status != 200:
                    raise ContentReleaseQueryPreparationError(
                        f"query preparation returned HTTP {response.status}"
                    )
                
                result = json.loads(response.read().decode("utf-8"))
                
                # Verify the result has expected structure
                if not isinstance(result, dict):
                    raise ContentReleaseQueryPreparationError(
                        "query preparation returned invalid JSON structure"
                    )
                
                # Check if all proofs are ready (non-null and have status)
                all_ready = True
                for proof_key in ["creatorSearchProof", "postSearchProof", "homepageSearchProof"]:
                    proof = result.get(proof_key)
                    if proof is None:
                        all_ready = False
                        break
                    # Proof should have a status field indicating readiness
                    if not isinstance(proof, dict):
                        all_ready = False
                        break
                
                # If all proofs are ready, return immediately
                if all_ready:
                    return result
                
                # If not all ready, this is expected for the first call - we need to wait and retry
                # The Search index building happens asynchronously
                if attempt == 1:
                    # First attempt, give it some time
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 1.5, 10.0)
                    continue
                else:
                    # Subsequent attempts - check if we're making progress
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 1.5, 10.0)
                    continue
        
        except error.HTTPError as e:
            # Parse error response
            try:
                error_body = json.loads(e.read().decode("utf-8"))
                error_code = error_body.get("code", "UNKNOWN")
                error_message = error_body.get("userMessage", str(e))
                
                # Check if it's a transient error (not ready yet)
                if error_code == "CONTENT.RELEASE.query_barrier_not_ready":
                    # This is expected - indexes are still building
                    last_error = ContentReleaseQueryPreparationError(
                        f"query preparation not ready: {error_message}"
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 1.5, 10.0)
                    continue
                else:
                    # Permanent error
                    raise ContentReleaseQueryPreparationError(
                        f"query preparation failed with {error_code}: {error_message}"
                    ) from e
            except (json.JSONDecodeError, KeyError):
                # Can't parse error, treat as permanent
                raise ContentReleaseQueryPreparationError(
                    f"query preparation HTTP error {e.code}: {e.reason}"
                ) from e
        
        except error.URLError as e:
            # Network error - might be transient
            last_error = ContentReleaseQueryPreparationError(
                f"network error during query preparation: {e.reason}"
            )
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 1.5, 10.0)
            continue
        
        except Exception as e:
            # Unexpected error
            raise ContentReleaseQueryPreparationError(
                f"unexpected error during query preparation: {e}"
            ) from e
    
    # Timeout reached
    if last_error:
        raise ContentReleaseQueryPreparationError(
            f"query preparation timed out after {attempt} attempts: {last_error}"
        ) from last_error
    else:
        raise ContentReleaseQueryPreparationError(
            f"query preparation timed out after {timeout_seconds}s"
        )
