package runtimesync

import (
	"context"
	"fmt"
	"strings"

	personarollout "quwoquan_service/runtime/persona"
)

var personaPatchTypes = map[string]struct{}{
	personarollout.PatchPersonaActivated:      {},
	personarollout.PatchPersonaProfileUpdated: {},
	personarollout.PatchPersonaRetired:        {},
}

func PersonaPatchTypes() []string {
	return []string{
		personarollout.PatchPersonaActivated,
		personarollout.PatchPersonaProfileUpdated,
		personarollout.PatchPersonaRetired,
	}
}

func IsPersonaPatchType(patchType string) bool {
	_, ok := personaPatchTypes[strings.TrimSpace(patchType)]
	return ok
}

func (s *Service) AppendPersonaPatch(
	ctx context.Context,
	userID string,
	patchType string,
	payload map[string]any,
) (Patch, error) {
	if !IsPersonaPatchType(patchType) {
		return Patch{}, fmt.Errorf("unsupported persona patch type: %s", patchType)
	}
	if strings.TrimSpace(anyPayloadString(payload["personaId"])) == "" {
		return Patch{}, fmt.Errorf("personaId is required for persona patch")
	}
	return s.AppendPatch(ctx, userID, patchType, payload)
}

func anyPayloadString(value any) string {
	switch v := value.(type) {
	case string:
		return v
	default:
		return ""
	}
}
