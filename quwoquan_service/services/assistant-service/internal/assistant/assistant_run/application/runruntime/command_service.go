package runruntime

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

type SessionResolver interface {
	ResolveAuthorizedSession(
		context.Context,
		string,
		string,
	) (SessionContinuity, error)
}

type SessionResolverFunc func(
	context.Context,
	string,
	string,
) (SessionContinuity, error)

func (f SessionResolverFunc) ResolveAuthorizedSession(
	ctx context.Context,
	userID string,
	sessionID string,
) (SessionContinuity, error) {
	return f(ctx, userID, sessionID)
}

type CommandServiceOption func(*CommandService)

// CommandService is the only writable AssistantRun command surface. Every
// mutation loads one aggregate revision and commits its journal event with CAS.
type CommandService struct {
	repository      Repository
	sessions        SessionResolver
	skillPackages   SkillPackageIdentityResolver
	startAccess     StartAccessPolicy
	policies        PolicyResolver
	feedbackContext FeedbackContextResolver
	now             func() time.Time
	newRunID        func() (string, error)
	cancel          *CancellationCoordinator
}

func NewCommandService(
	repository Repository,
	sessions SessionResolver,
	skillPackages SkillPackageIdentityResolver,
	startAccess StartAccessPolicy,
	now func() time.Time,
	cancel *CancellationCoordinator,
	options ...CommandServiceOption,
) *CommandService {
	if repository == nil || sessions == nil || skillPackages == nil || startAccess == nil {
		panic("assistant run command dependencies are required")
	}
	if now == nil {
		now = time.Now
	}
	service := &CommandService{
		repository:    repository,
		sessions:      sessions,
		skillPackages: skillPackages,
		startAccess:   startAccess,
		now:           now,
		newRunID:      newRunID,
		cancel:        cancel,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

func (s *CommandService) Get(
	ctx context.Context,
	userID string,
	runID string,
) (Run, error) {
	run, err := s.repository.Load(ctx, strings.TrimSpace(runID))
	if err != nil {
		return Run{}, err
	}
	if run.UserID != strings.TrimSpace(userID) {
		return Run{}, ErrRunNotFound
	}
	return run, nil
}

func (s *CommandService) EventsAfter(
	ctx context.Context,
	userID string,
	runID string,
	afterSequence int64,
	limit int,
) ([]JournalEvent, error) {
	if _, err := s.Get(ctx, userID, runID); err != nil {
		return nil, err
	}
	return s.repository.EventsAfter(ctx, runID, afterSequence, limit)
}

func (s *CommandService) mutate(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	eventKind string,
	commandPayload any,
	change func(*Run, time.Time) error,
) (Run, error) {
	return s.mutateWithIdempotencyConflict(
		ctx,
		userID,
		runID,
		commandID,
		eventKind,
		commandPayload,
		ErrRevisionConflict,
		change,
	)
}

func (s *CommandService) mutateWithIdempotencyConflict(
	ctx context.Context,
	userID string,
	runID string,
	commandID string,
	eventKind string,
	commandPayload any,
	idempotencyConflict error,
	change func(*Run, time.Time) error,
) (Run, error) {
	commandID = strings.TrimSpace(commandID)
	if commandID == "" {
		return Run{}, ErrInvalidRun
	}
	payloadDigest, err := commandDigest(eventKind, commandPayload)
	if err != nil {
		return Run{}, err
	}
	receipt, err := s.repository.LoadCommandReceipt(ctx, runID, commandID)
	if err == nil {
		if receipt.CommandKind != eventKind ||
			receipt.PayloadDigest != payloadDigest {
			return Run{}, idempotencyConflict
		}
		return s.Get(ctx, userID, runID)
	}
	if !errors.Is(err, ErrRunNotFound) {
		return Run{}, err
	}
	run, err := s.Get(ctx, userID, runID)
	if err != nil {
		return Run{}, err
	}
	lastSequence := run.JournalSequence
	expectedRevision := run.Revision
	now := s.now().UTC().Truncate(time.Millisecond)
	if err := change(&run, now); err != nil {
		return Run{}, err
	}
	if run.Revision == expectedRevision {
		return run, nil
	}
	event := JournalEvent{
		EventID:   run.RunID + ":" + int64String(lastSequence+1),
		RunID:     run.RunID,
		Sequence:  lastSequence + 1,
		Revision:  run.Revision,
		Kind:      eventKind,
		Payload:   map[string]any{"status": run.State.WireName()},
		CreatedAt: now,
	}
	run.JournalSequence = event.Sequence
	if err := s.repository.Commit(
		ctx,
		expectedRevision,
		run,
		[]JournalEvent{event},
		&CommandReceipt{
			RunID:         run.RunID,
			CommandID:     commandID,
			CommandKind:   eventKind,
			PayloadDigest: payloadDigest,
			Revision:      run.Revision,
			CreatedAt:     now,
		},
	); err != nil {
		// A concurrent retry may have committed the command receipt after this
		// request's initial lookup. Resolve that exact race from the durable
		// receipt; unrelated aggregate CAS conflicts remain revision conflicts.
		if errors.Is(err, ErrRevisionConflict) {
			receipt, receiptErr := s.repository.LoadCommandReceipt(
				ctx,
				runID,
				commandID,
			)
			if receiptErr == nil {
				if receipt.CommandKind != eventKind ||
					receipt.PayloadDigest != payloadDigest {
					return Run{}, idempotencyConflict
				}
				return s.Get(ctx, userID, runID)
			}
		}
		return Run{}, err
	}
	return run, nil
}

func commandDigest(kind string, payload any) (string, error) {
	encoded, err := json.Marshal(struct {
		Kind    string `json:"kind"`
		Payload any    `json:"payload"`
	}{
		Kind:    strings.TrimSpace(kind),
		Payload: payload,
	})
	if err != nil {
		return "", ErrInvalidRun
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func newRunID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return "arn_" + hex.EncodeToString(buffer), nil
}

func int64String(value int64) string {
	if value == 0 {
		return "0"
	}
	var buffer [20]byte
	index := len(buffer)
	for value > 0 {
		index--
		buffer[index] = byte('0' + value%10)
		value /= 10
	}
	return string(buffer[index:])
}
