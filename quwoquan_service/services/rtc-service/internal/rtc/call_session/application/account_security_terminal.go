package application

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/event"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

const (
	accountSecurityTerminalActor       = "system:rtc-account-security"
	accountSecurityTerminalCommandName = "TerminateForAccountSecurity"
	accountSecurityTerminalBatchSize   = 100
)

// AccountSecurityTerminalEvent is the minimal, service-owned projection of a
// durable UserAccount security fact. It intentionally never retains upstream
// payload bytes, decision references, or user profile data.
type AccountSecurityTerminalEvent struct {
	EventID      string
	AccountID    string
	PersonaIDs   []string
	AccountState string
	AuthEpoch    int64
	OccurredAt   time.Time
}

type AccountSecurityTerminalApplyResult struct {
	TerminatedCalls int
	Replayed        bool
	RestoredIgnored bool
}

func (event AccountSecurityTerminalEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AccountID) == "" ||
		event.OccurredAt.IsZero() {
		return errors.New("incomplete account security terminal event")
	}
	switch strings.TrimSpace(event.AccountState) {
	case "closed":
		if len(normalizeAccountSecurityPersonaIDs(event.PersonaIDs)) == 0 {
			return errors.New("closed account security terminal event has no personas")
		}
	case "suspended":
		if event.AuthEpoch <= 0 ||
			len(normalizeAccountSecurityPersonaIDs(event.PersonaIDs)) == 0 {
			return errors.New("invalid suspended account security terminal event")
		}
	case "active":
		if event.AuthEpoch <= 0 {
			return errors.New("invalid restored account security event")
		}
	default:
		return errors.New("invalid account security terminal state")
	}
	return nil
}

// ApplyAccountSecurityTerminalEvent ends every active CallSession for any
// affected persona. Room deletion happens before the terminal state commit, so
// an unavailable media provider leaves the source event pending for recovery
// rather than acknowledging an active media room.
//
// A UserRestored event is deliberately acknowledged as a no-op: it may restore
// admission for future calls, but it never restores any historical session,
// room, access material, or participant membership.
func (o *CallOrchestrator) ApplyAccountSecurityTerminalEvent(
	ctx context.Context,
	securityEvent AccountSecurityTerminalEvent,
) (AccountSecurityTerminalApplyResult, error) {
	if err := securityEvent.Validate(); err != nil {
		return AccountSecurityTerminalApplyResult{}, err
	}
	if securityEvent.AccountState == "active" {
		return AccountSecurityTerminalApplyResult{
			Replayed:        true,
			RestoredIgnored: true,
		}, nil
	}

	personaIDs := normalizeAccountSecurityPersonaIDs(securityEvent.PersonaIDs)
	result := AccountSecurityTerminalApplyResult{}
	for {
		sessions, err := o.repo.FindActiveCallsForUsers(
			ctx,
			personaIDs,
			accountSecurityTerminalBatchSize,
		)
		if err != nil {
			return result, fmt.Errorf(
				"find account security terminal call candidates: %w",
				err,
			)
		}
		if len(sessions) == 0 {
			result.Replayed = result.TerminatedCalls == 0
			return result, nil
		}

		seen := make(map[string]struct{}, len(sessions))
		changedThisBatch := 0
		for _, session := range sessions {
			if session == nil || strings.TrimSpace(session.ID) == "" {
				continue
			}
			if _, duplicate := seen[session.ID]; duplicate {
				continue
			}
			seen[session.ID] = struct{}{}

			outcome, err := o.terminateForAccountSecurity(
				ctx,
				session,
				securityEvent,
			)
			if err != nil {
				return result, err
			}
			if outcome.Changed {
				changedThisBatch++
				result.TerminatedCalls++
			}
		}
		if changedThisBatch == 0 {
			// A concurrent terminal command may have ended every candidate
			// between the named query and its CAS reload. A fresh delivery can
			// safely retry if any non-ended session remains.
			result.Replayed = result.TerminatedCalls == 0
			return result, nil
		}
	}
}

func (o *CallOrchestrator) terminateForAccountSecurity(
	ctx context.Context,
	candidate *model.CallSession,
	securityEvent AccountSecurityTerminalEvent,
) (mutationOutcome, error) {
	if candidate == nil || strings.TrimSpace(candidate.ID) == "" {
		return mutationOutcome{}, errors.New("invalid account security call candidate")
	}
	if o.roomService == nil {
		return mutationOutcome{}, errors.New("account security room revocation unavailable")
	}
	// Deleting the room is the provider's atomic member eviction. It both
	// disconnects existing participants and prevents this service from
	// retaining a room/access handle while the durable event is pending.
	if err := o.roomService.DeleteRoom(ctx, candidate.RoomID); err != nil {
		return mutationOutcome{}, fmt.Errorf(
			"revoke account security media room access: %w",
			err,
		)
	}
	// Cache cleanup must not precede media revocation: a Redis outage must
	// leave this delivery pending, but can never leave an active room because
	// cache maintenance happened first. A retry repeats idempotent room delete
	// and clears residual state before the terminal outbox commit.
	if o.cache != nil {
		if err := o.cache.DeleteCallState(ctx, candidate.ID); err != nil {
			return mutationOutcome{}, fmt.Errorf(
				"clear account security call cache: %w",
				err,
			)
		}
	}

	endReason := model.EndReasonAccountClosed
	if securityEvent.AccountState == "suspended" {
		endReason = model.EndReasonAccountSuspended
	}
	return o.mutateCommand(ctx, candidate.ID, mutationCommand{
		actorID:              accountSecurityTerminalActor,
		idempotencyKey:       accountSecurityTerminalIdempotencyKey(securityEvent.EventID, candidate.ID),
		commandName:          accountSecurityTerminalCommandName,
		digest:               commandDigest(accountSecurityTerminalCommandName, securityEvent.EventID),
		requireParticipant:   false,
		skipEndedRoomCleanup: true,
	}, func(session *model.CallSession) (string, CallEventPayload, error) {
		changed, err := o.domainService.TerminateForAccountSecurity(
			session,
			endReason,
			o.now().UTC(),
		)
		if err != nil {
			return "", CallEventPayload{}, err
		}
		if !changed {
			return "", CallEventPayload{}, errNoop
		}
		return event.CallEnded, CallEventPayload{EndReason: session.EndReason}, nil
	})
}

func normalizeAccountSecurityPersonaIDs(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	sort.Strings(normalized)
	return normalized
}

func accountSecurityTerminalIdempotencyKey(eventID, callID string) string {
	return "rtc-call:account-security:" + commandDigest(
		accountSecurityTerminalCommandName,
		strings.TrimSpace(eventID)+"\x00"+strings.TrimSpace(callID),
	)
}
