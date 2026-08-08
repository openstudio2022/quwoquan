package runruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

const stopHookClaimLease = time.Minute

var ErrStopHookClaimLost = errors.New("assistant run stop hook claim lost")

// StopHookInvocation is the bounded immutable task written alongside the Run
// transition. It intentionally excludes prompts, tool payloads, credentials,
// and mutable Run state; InvocationID is the downstream idempotency key.
type StopHookInvocation struct {
	InvocationID         string
	RunID                string
	Phase                HookPhase
	Outcome              string
	RunRevision          int64
	ProtectedFactsDigest string
	Data                 map[string]any
	CreatedAt            time.Time
	AttemptCount         int
}

type StopHookStore interface {
	ClaimPendingStopHooks(
		context.Context,
		string,
		time.Time,
		time.Duration,
		int,
	) ([]StopHookInvocation, error)
	AcknowledgeStopHook(context.Context, string, string, time.Time, string) error
	ScheduleStopHookRetry(
		context.Context, string, string, time.Time, time.Time, string,
	) error
	ReleaseStopHookClaim(context.Context, string, string) error
}

type StopHookRelayOption func(*StopHookRelay)

func WithStopHookRelayClock(now func() time.Time) StopHookRelayOption {
	return func(relay *StopHookRelay) {
		if now != nil {
			relay.now = now
		}
	}
}

// StopHookRelay delivers HookOnStop after the owning Run transaction commits.
// Delivery is at-least-once; hooks receive the same InvocationID on every
// replay so external effects can make their receipt write idempotent.
type StopHookRelay struct {
	store     StopHookStore
	hooks     *HookRegistry
	ownerID   string
	interval  time.Duration
	batchSize int
	now       func() time.Time
	logger    *slog.Logger

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewStopHookRelay(
	store StopHookStore,
	hooks *HookRegistry,
	ownerID string,
	interval time.Duration,
	batchSize int,
	options ...StopHookRelayOption,
) *StopHookRelay {
	ownerID = strings.TrimSpace(ownerID)
	if store == nil || hooks == nil || ownerID == "" || interval <= 0 {
		panic("assistant run stop hook relay dependencies are required")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	relay := &StopHookRelay{
		store:     store,
		hooks:     hooks,
		ownerID:   ownerID,
		interval:  interval,
		batchSize: batchSize,
		now:       time.Now,
		logger:    slog.Default(),
	}
	for _, option := range options {
		if option != nil {
			option(relay)
		}
	}
	return relay
}

func (relay *StopHookRelay) Run(ctx context.Context) {
	if relay == nil {
		return
	}
	relay.flushAndObserve(ctx)
	ticker := time.NewTicker(relay.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			relay.flushAndObserve(ctx)
		}
	}
}

func (relay *StopHookRelay) FlushOnce(ctx context.Context) (int, error) {
	now := relay.now().UTC()
	invocations, err := relay.store.ClaimPendingStopHooks(
		ctx,
		relay.ownerID,
		now,
		stopHookClaimLease,
		relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for index, invocation := range invocations {
		input, err := stopHookInput(invocation)
		if err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, invocation, "invalid_invocation"),
				relay.releaseClaims(ctx, invocations[index+1:]),
			)
		}
		result, err := relay.hooks.Run(ctx, input)
		if err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, invocation, "hook_failed"),
				relay.releaseClaims(ctx, invocations[index+1:]),
			)
		}
		receiptDigest, err := stopHookReceiptDigest(invocation, result)
		if err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, invocation, "receipt_failed"),
				relay.releaseClaims(ctx, invocations[index+1:]),
			)
		}
		if err := relay.store.AcknowledgeStopHook(
			ctx,
			invocation.InvocationID,
			relay.ownerID,
			relay.now().UTC(),
			receiptDigest,
		); err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, invocation, "checkpoint_failed"),
				relay.releaseClaims(ctx, invocations[index+1:]),
			)
		}
		processed++
	}
	return processed, nil
}

func stopHookInput(invocation StopHookInvocation) (HookInput, error) {
	invocation.InvocationID = strings.TrimSpace(invocation.InvocationID)
	invocation.RunID = strings.TrimSpace(invocation.RunID)
	invocation.Outcome = strings.TrimSpace(invocation.Outcome)
	invocation.ProtectedFactsDigest = strings.TrimSpace(invocation.ProtectedFactsDigest)
	if invocation.Phase != HookOnStop || invocation.CreatedAt.IsZero() ||
		StableHookInvocationID(
			invocation.RunID,
			invocation.Phase,
			invocation.RunRevision,
		) != invocation.InvocationID ||
		!validStopHookDigest(invocation.ProtectedFactsDigest) ||
		!stopHookOutcome(invocation.Outcome) {
		return HookInput{}, ErrInvalidRun
	}
	state, err := generated.ParseAssistantRunState(invocation.Outcome)
	if err != nil {
		return HookInput{}, ErrInvalidRun
	}
	data := cloneMap(invocation.Data)
	if outcome, ok := data["outcome"].(string); !ok ||
		strings.TrimSpace(outcome) != invocation.Outcome {
		return HookInput{}, ErrInvalidRun
	}
	return HookInput{
		InvocationID:         invocation.InvocationID,
		Phase:                HookOnStop,
		Run:                  Run{RunID: invocation.RunID, Revision: invocation.RunRevision, State: state},
		RunRevision:          invocation.RunRevision,
		Outcome:              invocation.Outcome,
		TaskID:               "task_root",
		Data:                 data,
		ProtectedFactsDigest: invocation.ProtectedFactsDigest,
	}, nil
}

func stopHookReceiptDigest(
	invocation StopHookInvocation,
	result HookResult,
) (string, error) {
	digest, err := commandDigest("assistant_run_stop_hook_receipt", struct {
		InvocationID         string       `json:"invocationId"`
		Phase                HookPhase    `json:"phase"`
		Outcome              string       `json:"outcome"`
		RunRevision          int64        `json:"runRevision"`
		Decision             HookDecision `json:"decision"`
		ProtectedFactsDigest string       `json:"protectedFactsDigest"`
	}{
		InvocationID:         strings.TrimSpace(invocation.InvocationID),
		Phase:                invocation.Phase,
		Outcome:              strings.TrimSpace(invocation.Outcome),
		RunRevision:          invocation.RunRevision,
		Decision:             result.Decision,
		ProtectedFactsDigest: strings.TrimSpace(result.ProtectedFactsDigest),
	})
	if err != nil {
		return "", err
	}
	return "sha256:" + digest, nil
}

func validStopHookDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") {
		return false
	}
	decoded, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil && len(decoded) == sha256.Size
}

func stopHookOutcome(value string) bool {
	switch strings.TrimSpace(value) {
	case "completed", "failed", "cancelled", "paused",
		"waiting_user", "waiting_approval", "waiting_external":
		return true
	default:
		return false
	}
}

func (relay *StopHookRelay) scheduleRetry(
	ctx context.Context,
	invocation StopHookInvocation,
	failureCode string,
) error {
	failedAt := relay.now().UTC()
	return relay.store.ScheduleStopHookRetry(
		ctx,
		invocation.InvocationID,
		relay.ownerID,
		failedAt,
		failedAt.Add(stopHookRetryDelay(invocation.AttemptCount)),
		failureCode,
	)
}

func stopHookRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}

func (relay *StopHookRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("assistant run stop hook relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastSuccessfulScan := relay.lastSuccessfulScan
	lastFailure := relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulScan.IsZero() {
		return errors.New("assistant run stop hook relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant run stop hook relay heartbeat is stale")
	}
	return nil
}

func (relay *StopHookRelay) flushAndObserve(ctx context.Context) {
	processed, err := relay.FlushOnce(ctx)
	if err != nil {
		relay.recordFailure(err)
		relay.logger.ErrorContext(
			ctx,
			"assistant run stop hook relay failed",
			slog.String("error", err.Error()),
		)
		return
	}
	relay.recordSuccessfulScan()
	if processed == relay.batchSize {
		relay.logger.WarnContext(
			ctx,
			"assistant run stop hook relay remains backlogged",
			slog.Int("batchSize", relay.batchSize),
		)
	}
}

func (relay *StopHookRelay) recordSuccessfulScan() {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *StopHookRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastFailure = err
}

func (relay *StopHookRelay) releaseClaims(
	ctx context.Context,
	invocations []StopHookInvocation,
) error {
	var result error
	for _, invocation := range invocations {
		result = errors.Join(
			result,
			relay.store.ReleaseStopHookClaim(
				ctx,
				invocation.InvocationID,
				relay.ownerID,
			),
		)
	}
	return result
}
