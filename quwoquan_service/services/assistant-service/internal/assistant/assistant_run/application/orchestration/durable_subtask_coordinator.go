package orchestration

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// DurableSubtaskOutcome is the terminal state persisted for one child
// TaskNode. It deliberately mirrors the existing Task/RunItem terminal states
// instead of creating a second child aggregate.
type DurableSubtaskOutcome string

const (
	DurableSubtaskCompleted DurableSubtaskOutcome = "completed"
	DurableSubtaskFailed    DurableSubtaskOutcome = "failed"
)

// DurableSubtaskRequest identifies the already-persisted TaskNode produced by
// the AgentLoop process projection. InputDigest is a canonical digest of the
// frozen child plan, so a replan cannot consume a receipt from different work.
type DurableSubtaskRequest struct {
	RunID       string
	TaskID      string
	OwnerAgent  string
	InputDigest string
}

// DurableSubtaskClaim is an opaque fenced capability. Only the claim owner
// holding the current token may heartbeat or commit a terminal receipt.
type DurableSubtaskClaim struct {
	RunID          string
	TaskID         string
	ClaimID        string
	ClaimOwner     string
	InputDigest    string
	FencingToken   int64
	Attempt        int
	IdempotencyKey string
	LeaseExpiresAt time.Time
}

// DurableSubtaskResult is the public-safe child result stored in the existing
// RunItem journal. Payload may contain conclusions, counts and canonical
// references, but never provider diagnostics, tool inputs or model reasoning.
type DurableSubtaskResult struct {
	Outcome      DurableSubtaskOutcome
	Summary      string
	FailureCode  string
	Payload      map[string]any
	ArtifactRefs []string
}

// DurableSubtaskTerminalReceipt is the immutable result read by the Manager.
// The Manager may synthesize only after every child returned such a receipt.
type DurableSubtaskTerminalReceipt struct {
	ReceiptRef        string
	RunID             string
	TaskID            string
	InputDigest       string
	Outcome           DurableSubtaskOutcome
	Attempt           int
	FencingToken      int64
	IdempotencyKey    string
	Summary           string
	FailureCode       string
	ResultArtifactRef string
	Payload           map[string]any
	CompletedAt       time.Time
}

// DurableSubtaskStore persists claims and terminal receipts by CAS-mutating the
// owning AssistantRun. Implementations must not create a child collection or a
// second aggregate.
type DurableSubtaskStore interface {
	Claim(
		context.Context,
		DurableSubtaskRequest,
		string,
		time.Duration,
	) (DurableSubtaskClaim, *DurableSubtaskTerminalReceipt, error)
	Heartbeat(context.Context, DurableSubtaskClaim, time.Duration) error
	Finish(
		context.Context,
		DurableSubtaskClaim,
		DurableSubtaskResult,
	) (DurableSubtaskTerminalReceipt, error)
}

type DurableSubtaskWork func(
	context.Context,
	DurableSubtaskClaim,
) (DurableSubtaskResult, error)

type DurableSubtaskCoordinator struct {
	store             DurableSubtaskStore
	workerID          string
	leaseTTL          time.Duration
	heartbeatInterval time.Duration
}

func NewDurableSubtaskCoordinator(
	store DurableSubtaskStore,
	workerID string,
	leaseTTL time.Duration,
	heartbeatInterval time.Duration,
) *DurableSubtaskCoordinator {
	workerID = strings.TrimSpace(workerID)
	if store == nil || workerID == "" || leaseTTL <= 0 ||
		heartbeatInterval <= 0 || heartbeatInterval >= leaseTTL {
		panic("assistant durable subtask dependencies are required")
	}
	return &DurableSubtaskCoordinator{
		store:             store,
		workerID:          workerID,
		leaseTTL:          leaseTTL,
		heartbeatInterval: heartbeatInterval,
	}
}

// Execute claims one existing TaskNode, keeps its lease alive, and commits one
// terminal receipt. A completed receipt is returned without invoking work, so
// process restart never repeats an already-completed child. Cancellation of the
// parent context intentionally leaves the claim non-terminal; its lease expiry
// is the recovery boundary for another worker.
func (c *DurableSubtaskCoordinator) Execute(
	ctx context.Context,
	request DurableSubtaskRequest,
	work DurableSubtaskWork,
) (DurableSubtaskTerminalReceipt, error) {
	if c == nil || c.store == nil || work == nil ||
		!validDurableSubtaskRequest(request) {
		return DurableSubtaskTerminalReceipt{}, fmt.Errorf(
			"invalid durable subtask request",
		)
	}
	claim, terminal, err := c.store.Claim(
		ctx,
		request,
		c.workerID,
		c.leaseTTL,
	)
	if err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	if terminal != nil {
		if !sameDurableSubtaskTerminal(request, *terminal) {
			return DurableSubtaskTerminalReceipt{}, fmt.Errorf(
				"durable subtask terminal receipt does not match frozen input",
			)
		}
		return cloneDurableSubtaskTerminal(*terminal), nil
	}

	workCtx, cancelWork := context.WithCancel(ctx)
	heartbeatDone := make(chan error, 1)
	go c.heartbeat(workCtx, claim, cancelWork, heartbeatDone)

	result, workErr := work(workCtx, claim)
	cancelWork()
	heartbeatErr := <-heartbeatDone
	if heartbeatErr != nil {
		return DurableSubtaskTerminalReceipt{}, heartbeatErr
	}
	if ctx.Err() != nil {
		// A cancelled worker must not turn an interrupted child into a durable
		// failure. The current fencing token expires and another worker resumes.
		return DurableSubtaskTerminalReceipt{}, ctx.Err()
	}
	if workErr != nil {
		result = DurableSubtaskResult{
			Outcome:     DurableSubtaskFailed,
			Summary:     "subagent execution failed",
			FailureCode: "subagent_execution_failed",
		}
	}
	if err := validateDurableSubtaskResult(result); err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	terminalReceipt, err := c.store.Finish(
		context.WithoutCancel(ctx),
		claim,
		result,
	)
	if err != nil {
		return DurableSubtaskTerminalReceipt{}, err
	}
	if !sameDurableSubtaskTerminal(request, terminalReceipt) {
		return DurableSubtaskTerminalReceipt{}, fmt.Errorf(
			"durable subtask terminal receipt does not match frozen input",
		)
	}
	if workErr != nil {
		return terminalReceipt, workErr
	}
	return terminalReceipt, nil
}

func (c *DurableSubtaskCoordinator) heartbeat(
	ctx context.Context,
	claim DurableSubtaskClaim,
	cancelWork context.CancelFunc,
	done chan<- error,
) {
	ticker := time.NewTicker(c.heartbeatInterval)
	defer ticker.Stop()
	defer close(done)
	for {
		select {
		case <-ctx.Done():
			done <- nil
			return
		case <-ticker.C:
			if err := c.store.Heartbeat(ctx, claim, c.leaseTTL); err != nil {
				if ctx.Err() != nil {
					done <- nil
					return
				}
				cancelWork()
				done <- err
				return
			}
		}
	}
}

func validDurableSubtaskRequest(request DurableSubtaskRequest) bool {
	return strings.TrimSpace(request.RunID) != "" &&
		strings.TrimSpace(request.TaskID) != "" &&
		strings.HasPrefix(strings.TrimSpace(request.OwnerAgent), "subagent:") &&
		validSHA256Digest(request.InputDigest)
}

func validSHA256Digest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+64 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, char := range strings.TrimPrefix(value, "sha256:") {
		if !(char >= '0' && char <= '9') && !(char >= 'a' && char <= 'f') {
			return false
		}
	}
	return true
}

func validateDurableSubtaskResult(result DurableSubtaskResult) error {
	switch result.Outcome {
	case DurableSubtaskCompleted:
		if strings.TrimSpace(result.Summary) == "" || len(result.Payload) == 0 {
			return errors.New("completed durable subtask requires a safe result")
		}
	case DurableSubtaskFailed:
		if strings.TrimSpace(result.FailureCode) == "" {
			return errors.New("failed durable subtask requires a stable failure code")
		}
	default:
		return errors.New("durable subtask outcome is not terminal")
	}
	return nil
}

func sameDurableSubtaskTerminal(
	request DurableSubtaskRequest,
	receipt DurableSubtaskTerminalReceipt,
) bool {
	return strings.TrimSpace(receipt.RunID) == strings.TrimSpace(request.RunID) &&
		strings.TrimSpace(receipt.TaskID) == strings.TrimSpace(request.TaskID) &&
		strings.TrimSpace(receipt.InputDigest) == strings.TrimSpace(request.InputDigest) &&
		strings.TrimSpace(receipt.ReceiptRef) != "" &&
		strings.TrimSpace(receipt.IdempotencyKey) != "" &&
		strings.TrimSpace(receipt.ResultArtifactRef) != "" &&
		!receipt.CompletedAt.IsZero()
}

func cloneDurableSubtaskTerminal(
	receipt DurableSubtaskTerminalReceipt,
) DurableSubtaskTerminalReceipt {
	receipt.Payload = cloneSubtaskPayload(receipt.Payload)
	return receipt
}

func cloneSubtaskPayload(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	cloned := make(map[string]any, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}
