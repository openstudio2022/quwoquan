package application

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// applyPersonaProfileSync 把 source 的资料字段扇出同步到目标分身。
// 每个目标是一次独立的 Persona 聚合提交，使用从命令幂等键派生的
// per-target 重放身份（personas_command_receipts.idempotency_key 全局唯一）。
func (s *SubAccountService) applyPersonaProfileSync(
	ctx context.Context,
	ownerID string,
	source *model.Persona,
	personas []model.Persona,
	options PersonaProfileSyncOptions,
	fieldsMask []string,
	meta PersonaCommandMeta,
) (int, error) {
	if source == nil {
		return 0, ErrSubAccountNotFound
	}
	if isRetiredPersona(source) {
		return 0, ErrRetiredPersonaAction
	}
	if len(fieldsMask) == 0 {
		return 0, nil
	}
	targets := resolveSyncTargetPersonas(
		personas,
		source.SubAccountID,
		options.ApplyScope,
		options.SyncTargetIDs,
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
		if _, err := s.commands.CommitMutation(
			ctx,
			target,
			personaports.PersonaUpdatedEvent,
			derivePersonaSyncMeta(meta, target.SubAccountID),
		); err != nil {
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
