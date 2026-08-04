package releaseimport

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"

	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// CreatorPersonaCommandMeta derives the stable Persona command payload digest
// and the activation-run-scoped idempotency key from one immutable creator
// release fact.
func CreatorPersonaCommandMeta(
	state CreatorPersonaState,
	importRunID string,
) (personaports.PersonaCommandMeta, error) {
	normalizedRunID := strings.TrimSpace(importRunID)
	if normalizedRunID == "" {
		return personaports.PersonaCommandMeta{}, fmt.Errorf(
			"creator Persona import run ID is required",
		)
	}
	payload, err := json.Marshal(state)
	if err != nil {
		return personaports.PersonaCommandMeta{}, err
	}
	digest := sha256.Sum256(payload)
	keyDigest := sha256.Sum256([]byte(strings.Join([]string{
		"creator-release",
		state.ReleaseID,
		normalizedRunID,
		state.PersonaID,
	}, "\x00")))
	return personaports.PersonaCommandMeta{
		IdempotencyKey: "creator-release:" + hex.EncodeToString(keyDigest[:24]),
		CommandDigest:  hex.EncodeToString(digest[:]),
	}, nil
}
