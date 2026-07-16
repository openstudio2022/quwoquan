package application

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

func (s *SubAccountService) applyPersonaProfileSync(ctx context.Context, ownerID string, source *model.Persona, personas []model.Persona, data map[string]any, fieldsMask []string) (int, error) {
	if source == nil {
		return 0, ErrSubAccountNotFound
	}
	if isRetiredPersona(source) {
		return 0, ErrRetiredPersonaAction
	}
	if len(fieldsMask) == 0 {
		return 0, nil
	}
	applyScope, _ := data["applyScope"].(string)
	targets := resolveSyncTargetPersonas(
		personas,
		source.SubAccountID,
		applyScope,
		extractSyncTargetIDs(data),
	)
	now := time.Now().UTC()
	applied := 0
	for _, target := range targets {
		applyFieldsFromSource(target, source, fieldsMask)
		target.OverriddenProfileFields = encodeProfileFieldList(
			removeProfileFields(parseProfileFieldList(target.OverriddenProfileFields), fieldsMask),
		)
		target.InheritsProfileFromOwner = source.IsPrimary && len(parseProfileFieldList(target.OverriddenProfileFields)) == 0
		target.LastProfileSyncAt = &now
		target.LastProfileSyncSource = "manual_sync"
		normalizePersonaPersistence(target)
		if err := s.personas.Update(ctx, target); err != nil {
			if isPersonaHandleConflict(err) {
				return applied, ErrPersonaHandleTaken
			}
			return applied, err
		}
		applied++
	}
	_ = s.pcache.Del(ctx, ownerID)
	return applied, nil
}
