// Package skillconsent 提供测试树内的 SkillConsent typed double。
// 该包不参与任何环境 runtime composition。
package skillconsent

import (
	"context"
	"sync"

	"github.com/google/uuid"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
)

type MemoryStore struct {
	mu       sync.Mutex
	items    map[string]model.Consent
	receipts map[string]receipt
}

type receipt struct {
	operation string
	digest    string
	result    model.MutationResult
}

var _ ports.Store = (*MemoryStore)(nil)

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		items:    make(map[string]model.Consent),
		receipts: make(map[string]receipt),
	}
}

func (store *MemoryStore) ListActiveConsents(
	_ context.Context,
	accountID string,
) ([]model.Consent, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	items := make([]model.Consent, 0)
	for _, item := range store.items {
		if item.AccountID == accountID && item.RevokedAt == nil {
			items = append(items, item)
		}
	}
	return items, nil
}

func (store *MemoryStore) Apply(
	_ context.Context,
	command model.Command,
) (model.MutationResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	key := command.AccountID + "\x1f" + command.IdempotencyKey
	if stored, ok := store.receipts[key]; ok {
		if stored.operation != command.Operation || stored.digest != command.RequestDigest {
			return model.MutationResult{}, model.ErrIdempotencyConflict
		}
		result := stored.result
		result.Replayed = true
		return result, nil
	}
	var active *model.Consent
	for _, item := range store.items {
		item := item
		if item.AccountID == command.AccountID && item.SkillID == command.SkillID &&
			item.RevokedAt == nil {
			active = &item
			break
		}
	}
	result := model.MutationResult{}
	switch command.Operation {
	case model.CommandGrant:
		if active != nil {
			result.Consent = active
			break
		}
		consent := model.Consent{
			ID:           uuid.NewString(),
			AccountID:    command.AccountID,
			SkillID:      command.SkillID,
			GrantedScope: command.GrantedScope,
			GrantedAt:    command.OccurredAt,
		}
		store.items[consent.ID] = consent
		result.Consent = &consent
		result.Changed = true
	case model.CommandRevoke:
		if active != nil {
			revoked := command.OccurredAt
			active.RevokedAt = &revoked
			store.items[active.ID] = *active
			result.Consent = active
			result.Changed = true
		}
	default:
		return model.MutationResult{}, model.ErrInvalidArgument
	}
	store.receipts[key] = receipt{
		operation: command.Operation,
		digest:    command.RequestDigest,
		result:    result,
	}
	return result, nil
}
