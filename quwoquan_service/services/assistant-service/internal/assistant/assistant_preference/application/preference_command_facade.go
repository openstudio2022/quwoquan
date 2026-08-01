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
	preferenceerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_preference"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
)

const defaultRestoreWindow = 10 * time.Minute

type SessionOwnerReader interface {
	OwnedSessionExists(
		ctx context.Context,
		userID string,
		sessionID string,
	) (bool, error)
}

type SetPreferenceCommand struct {
	UserID          string
	Scope           string
	SessionID       string
	Kind            string
	Value           string
	SourceType      string
	SourceSessionID string
	Confirmed       bool
}

type CommandFacade struct {
	store         preferenceports.Store
	sessions      SessionOwnerReader
	now           func() time.Time
	restoreWindow time.Duration
}

func NewCommandFacade(
	store preferenceports.Store,
	sessions SessionOwnerReader,
) *CommandFacade {
	return &CommandFacade{
		store:         store,
		sessions:      sessions,
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
	scope, sessionID, kind, value, sourceType, sourceSessionID, normalizeErr :=
		preferencemodel.Normalize(
			command.Scope,
			command.SessionID,
			command.Kind,
			command.Value,
			command.SourceType,
			command.SourceSessionID,
			command.Confirmed,
		)
	if normalizeErr != nil {
		return preferencemodel.Fact{}, preferenceInvalidArgument(normalizeErr.Error())
	}
	if scope == preferencemodel.ScopeSession {
		if f == nil || f.sessions == nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(
				"assistant session owner reader is not configured",
			)
		}
		owned, ownerErr := f.sessions.OwnedSessionExists(
			ctx,
			userID,
			sessionID,
		)
		if ownerErr != nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(ownerErr.Error())
		}
		if !owned {
			return preferencemodel.Fact{}, preferenceNotFound()
		}
	}
	if preferencemodel.IsFactualKind(kind) &&
		sourceType == preferencemodel.SourceSessionConfirmed {
		if f == nil || f.sessions == nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(
				"assistant session owner reader is not configured",
			)
		}
		owned, ownerErr := f.sessions.OwnedSessionExists(
			ctx,
			userID,
			sourceSessionID,
		)
		if ownerErr != nil {
			return preferencemodel.Fact{}, preferenceStorageUnavailable(ownerErr.Error())
		}
		if !owned {
			return preferencemodel.Fact{}, preferenceNotFound()
		}
	}
	if f == nil || f.store == nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(
			"assistant preference store is not configured",
		)
	}
	preferenceID, generateErr := rtid.Generate(rtid.PrefixAssistantPreference)
	if generateErr != nil {
		return preferencemodel.Fact{}, preferenceStorageUnavailable(generateErr.Error())
	}
	now := f.now()
	var confirmedAt *time.Time
	if preferencemodel.IsFactualKind(kind) {
		confirmedAt = &now
	}
	fact, storeErr := f.store.Upsert(ctx, preferenceports.UpsertInput{
		PreferenceID:    preferenceID,
		UserID:          userID,
		Scope:           scope,
		SessionID:       sessionID,
		Kind:            kind,
		Value:           value,
		SourceType:      sourceType,
		SourceSessionID: sourceSessionID,
		ConfirmedAt:     confirmedAt,
		Now:             now,
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
	return preferenceerrors.AppErrorFromPreferenceInvalidArgument(debug)
}

func InvalidArgumentError(debug string) *rterr.AppError {
	return preferenceInvalidArgument(debug)
}

func preferenceNotFound() *rterr.AppError {
	return preferenceerrors.AppErrorFromPreferenceNotFound(
		"assistant preference not found",
	)
}

func preferenceRestoreExpired() *rterr.AppError {
	return preferenceerrors.AppErrorFromPreferenceRestoreExpired(
		"assistant preference restore window expired",
	)
}

func preferenceStorageUnavailable(debug string) *rterr.AppError {
	return preferenceerrors.AppErrorFromPreferenceStorageUnavailable(debug)
}

func IsInvalidPreference(err error) bool {
	return errors.Is(err, preferencemodel.ErrInvalidPreference)
}
