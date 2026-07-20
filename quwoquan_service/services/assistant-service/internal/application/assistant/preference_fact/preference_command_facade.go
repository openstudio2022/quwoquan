package preferencefact

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/ports"
	assistantgenerated "quwoquan_service/services/assistant-service/internal/generated"
)

const defaultRestoreWindow = 10 * time.Minute

type ConversationOwnerReader interface {
	OwnedConversationExists(
		ctx context.Context,
		userID string,
		conversationID string,
	) (bool, error)
}

type SetPreferenceCommand struct {
	UserID         string
	Scope          string
	ConversationID string
	Kind           string
	Value          string
	SourceType     string
}

type CommandFacade struct {
	store         preferenceports.Store
	conversations ConversationOwnerReader
	now           func() time.Time
	restoreWindow time.Duration
}

func NewCommandFacade(
	store preferenceports.Store,
	conversations ConversationOwnerReader,
) *CommandFacade {
	return &CommandFacade{
		store:         store,
		conversations: conversations,
		now:           func() time.Time { return time.Now().UTC() },
		restoreWindow: defaultRestoreWindow,
	}
}

func (f *CommandFacade) SetPreference(
	ctx context.Context,
	command SetPreferenceCommand,
) (_ preferencemodel.Fact, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.SetAssistantPreference",
		attribute.String("preference.scope", strings.TrimSpace(command.Scope)),
		attribute.String("preference.kind", strings.TrimSpace(command.Kind)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID := strings.TrimSpace(command.UserID)
	if userID == "" {
		return preferencemodel.Fact{}, preferenceInvalidArgument("missing trusted persona")
	}
	scope, conversationID, kind, value, sourceType, normalizeErr :=
		preferencemodel.Normalize(
			command.Scope,
			command.ConversationID,
			command.Kind,
			command.Value,
			command.SourceType,
		)
	if normalizeErr != nil {
		return preferencemodel.Fact{}, preferenceInvalidArgument(normalizeErr.Error())
	}
	if scope == preferencemodel.ScopeSession {
		if f == nil || f.conversations == nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(
				"assistant conversation owner reader is not configured",
			)
		}
		owned, ownerErr := f.conversations.OwnedConversationExists(
			ctx,
			userID,
			conversationID,
		)
		if ownerErr != nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(ownerErr.Error())
		}
		if !owned {
			return preferencemodel.Fact{}, preferenceInvalidArgument(
				"session preference conversation is not owned by persona",
			)
		}
	}
	if f == nil || f.store == nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(
			"assistant preference store is not configured",
		)
	}
	preferenceID, generateErr := rtid.Generate(rtid.PrefixAssistantPreferenceFact)
	if generateErr != nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(generateErr.Error())
	}
	fact, storeErr := f.store.Upsert(ctx, preferenceports.UpsertInput{
		PreferenceID:   preferenceID,
		UserID:         userID,
		Scope:          scope,
		ConversationID: conversationID,
		Kind:           kind,
		Value:          value,
		SourceType:     sourceType,
		Now:            f.now(),
	})
	if storeErr != nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(storeErr.Error())
	}
	return fact, nil
}

func (f *CommandFacade) RevokePreference(
	ctx context.Context,
	userID string,
	preferenceID string,
) (_ preferencemodel.Fact, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.RevokeAssistantPreference")
	defer func() { rtobs.EndSpan(span, err) }()

	return f.updatePreferenceStatus(
		ctx,
		strings.TrimSpace(userID),
		strings.TrimSpace(preferenceID),
		preferencemodel.StatusRevoked,
	)
}

func (f *CommandFacade) RestorePreference(
	ctx context.Context,
	userID string,
	preferenceID string,
) (_ preferencemodel.Fact, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.RestoreAssistantPreference")
	defer func() { rtobs.EndSpan(span, err) }()

	return f.updatePreferenceStatus(
		ctx,
		strings.TrimSpace(userID),
		strings.TrimSpace(preferenceID),
		preferencemodel.StatusActive,
	)
}

func (f *CommandFacade) updatePreferenceStatus(
	ctx context.Context,
	userID string,
	preferenceID string,
	target preferencemodel.Status,
) (preferencemodel.Fact, error) {
	if userID == "" || preferenceID == "" {
		return preferencemodel.Fact{}, preferenceNotFound()
	}
	if f == nil || f.store == nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(
			"assistant preference store is not configured",
		)
	}
	for attempt := 0; attempt < 2; attempt++ {
		current, found, getErr := f.store.GetOwned(ctx, userID, preferenceID)
		if getErr != nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(getErr.Error())
		}
		if !found {
			return preferencemodel.Fact{}, preferenceNotFound()
		}
		if current.Status == target {
			return current, nil
		}
		now := f.now()
		update := preferenceports.StatusUpdate{
			Status:    target,
			UpdatedAt: now,
		}
		if target == preferencemodel.StatusRevoked {
			deadline := now.Add(f.restoreWindow)
			update.RevokedAt = &now
			update.RevocationDeadline = &deadline
		} else {
			if current.Status != preferencemodel.StatusRevoked ||
				current.RevocationDeadline == nil ||
				!now.Before(*current.RevocationDeadline) {
				return preferencemodel.Fact{}, preferenceRestoreExpired()
			}
		}
		updated, matched, updateErr := f.store.UpdateStatus(
			ctx,
			userID,
			preferenceID,
			current.Version,
			update,
		)
		if updateErr != nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(updateErr.Error())
		}
		if matched {
			return updated, nil
		}
	}
	return preferencemodel.Fact{}, preferenceStorageUnavailable(
		"assistant preference optimistic concurrency exhausted",
	)
}

func preferenceInvalidArgument(debug string) *rterr.AppError {
	return assistantgenerated.AppErrorFromPreferenceInvalidArgument(debug)
}

func InvalidArgumentError(debug string) *rterr.AppError {
	return preferenceInvalidArgument(debug)
}

func preferenceNotFound() *rterr.AppError {
	return assistantgenerated.AppErrorFromPreferenceNotFound(
		"assistant preference not found",
	)
}

func preferenceRestoreExpired() *rterr.AppError {
	return assistantgenerated.AppErrorFromPreferenceRestoreExpired(
		"assistant preference restore window expired",
	)
}

func preferenceStorageUnavailable(debug string) *rterr.AppError {
	return assistantgenerated.AppErrorFromPreferenceStorageUnavailable(debug)
}

func IsInvalidPreference(err error) bool {
	return errors.Is(err, preferencemodel.ErrInvalidPreference)
}
