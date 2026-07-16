package main

import (
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
)

// verifiedTelemetryActorHash derives the only actor key accepted by client
// telemetry writes. The service never persists a caller-provided user ID.
func verifiedTelemetryActorHash(r *http.Request) (string, bool) {
	if r == nil {
		return "", false
	}
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", false
	}
	actorID, ok := principal.Actor.BusinessActorID()
	if !ok || strings.TrimSpace(actorID) == "" {
		return "", false
	}
	sum := sha256.Sum256([]byte(actorID))
	return hex.EncodeToString(sum[:]), true
}
