package orchestration

import (
	"context"
	"errors"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

const durableSubtaskCASAttempts = 8

// RepositoryDurableSubtaskStore persists child execution inside the owning
// AssistantRun snapshot and journal. It deliberately reuses the canonical Run
// repository instead of introducing a subtask collection or worker-local
// recovery table.
type RepositoryDurableSubtaskStore struct {
	repository runruntime.Repository
	now        func() time.Time
}

func NewRepositoryDurableSubtaskStore(
	repository runruntime.Repository,
	now func() time.Time,
) *RepositoryDurableSubtaskStore {
	if repository == nil {
		panic("assistant run repository is required for durable subtasks")
	}
	if now == nil {
		now = time.Now
	}
	return &RepositoryDurableSubtaskStore{repository: repository, now: now}
}

func (s *RepositoryDurableSubtaskStore) Claim(
	ctx context.Context,
	request DurableSubtaskRequest,
	workerID string,
	leaseTTL time.Duration,
) (DurableSubtaskClaim, *DurableSubtaskTerminalReceipt, error) {
	for attempt := 0; attempt < durableSubtaskCASAttempts; attempt++ {
		run, err := s.repository.Load(ctx, strings.TrimSpace(request.RunID))
		if err != nil {
			return DurableSubtaskClaim{}, nil, err
		}
		expectedRevision := run.Revision
		now := s.now().UTC()
		claim, terminal, err := run.ClaimDurableSubtask(
			runruntime.DurableSubtaskClaimRequest{
				TaskID:      request.TaskID,
				OwnerAgent:  request.OwnerAgent,
				InputDigest: request.InputDigest,
			},
			workerID,
			leaseTTL,
			now,
		)
		if err != nil {
			return DurableSubtaskClaim{}, nil, err
		}
		if terminal != nil {
			projected := projectDurableSubtaskTerminal(*terminal)
			return projectDurableSubtaskClaim(claim), &projected, nil
		}
		if err := s.commit(
			ctx,
			expectedRevision,
			run,
			"task_graph_patch",
			map[string]any{
				"status":       run.State.WireName(),
				"taskId":       claim.TaskID,
				"taskStatus":   "running",
				"attempt":      claim.Attempt,
				"fencingToken": claim.FencingToken,
			},
			now,
		); err == nil {
			return projectDurableSubtaskClaim(claim), nil, nil
		} else if !errors.Is(err, runruntime.ErrRevisionConflict) {
			return DurableSubtaskClaim{}, nil, err
		}
	}
	return DurableSubtaskClaim{}, nil, runruntime.ErrRevisionConflict
}

func (s *RepositoryDurableSubtaskStore) Heartbeat(
	ctx context.Context,
	claim DurableSubtaskClaim,
	leaseTTL time.Duration,
) error {
	for attempt := 0; attempt < durableSubtaskCASAttempts; attempt++ {
		run, err := s.repository.Load(ctx, strings.TrimSpace(claim.RunID))
		if err != nil {
			return err
		}
		expectedRevision := run.Revision
		now := s.now().UTC()
		updated, err := run.HeartbeatDurableSubtask(
			projectRuntimeDurableSubtaskClaim(claim),
			leaseTTL,
			now,
		)
		if err != nil {
			return err
		}
		if err := s.commit(
			ctx,
			expectedRevision,
			run,
			"task_graph_patch",
			map[string]any{
				"status":       run.State.WireName(),
				"taskId":       updated.TaskID,
				"taskStatus":   "running",
				"attempt":      updated.Attempt,
				"fencingToken": updated.FencingToken,
			},
			now,
		); err == nil {
			return nil
		} else if !errors.Is(err, runruntime.ErrRevisionConflict) {
			return err
		}
	}
	return runruntime.ErrRevisionConflict
}

func (s *RepositoryDurableSubtaskStore) Finish(
	ctx context.Context,
	claim DurableSubtaskClaim,
	result DurableSubtaskResult,
) (DurableSubtaskTerminalReceipt, error) {
	for attempt := 0; attempt < durableSubtaskCASAttempts; attempt++ {
		run, err := s.repository.Load(ctx, strings.TrimSpace(claim.RunID))
		if err != nil {
			return DurableSubtaskTerminalReceipt{}, err
		}
		expectedRevision := run.Revision
		now := s.now().UTC()
		receipt, err := run.FinishDurableSubtask(
			projectRuntimeDurableSubtaskClaim(claim),
			runruntime.DurableSubtaskResult{
				Outcome:      string(result.Outcome),
				Summary:      result.Summary,
				FailureCode:  result.FailureCode,
				Payload:      cloneSubtaskPayload(result.Payload),
				ArtifactRefs: append([]string(nil), result.ArtifactRefs...),
			},
			now,
		)
		if err != nil {
			return DurableSubtaskTerminalReceipt{}, err
		}
		if run.Revision == expectedRevision {
			return projectDurableSubtaskTerminal(receipt), nil
		}
		if err := s.commit(
			ctx,
			expectedRevision,
			run,
			"task_graph_patch",
			map[string]any{
				"status":       run.State.WireName(),
				"taskId":       receipt.TaskID,
				"taskStatus":   receipt.Outcome,
				"attempt":      receipt.Attempt,
				"fencingToken": receipt.FencingToken,
				"artifactRef":  receipt.ResultArtifactRef,
			},
			now,
		); err == nil {
			return projectDurableSubtaskTerminal(receipt), nil
		} else if !errors.Is(err, runruntime.ErrRevisionConflict) {
			return DurableSubtaskTerminalReceipt{}, err
		}
	}
	return DurableSubtaskTerminalReceipt{}, runruntime.ErrRevisionConflict
}

func (s *RepositoryDurableSubtaskStore) commit(
	ctx context.Context,
	expectedRevision int64,
	run runruntime.Run,
	eventKind string,
	payload map[string]any,
	now time.Time,
) error {
	run.JournalSequence++
	event := runruntime.JournalEvent{
		EventID:   run.RunID + ":" + strconv.FormatInt(run.JournalSequence, 10),
		RunID:     run.RunID,
		Sequence:  run.JournalSequence,
		Revision:  run.Revision,
		Kind:      strings.TrimSpace(eventKind),
		Payload:   cloneSubtaskPayload(payload),
		CreatedAt: now.UTC(),
	}
	return s.repository.Commit(
		ctx,
		expectedRevision,
		run,
		[]runruntime.JournalEvent{event},
		nil,
	)
}

func projectDurableSubtaskClaim(
	claim runruntime.DurableSubtaskClaim,
) DurableSubtaskClaim {
	return DurableSubtaskClaim{
		RunID:          claim.RunID,
		TaskID:         claim.TaskID,
		ClaimID:        claim.ClaimID,
		ClaimOwner:     claim.ClaimOwner,
		InputDigest:    claim.InputDigest,
		FencingToken:   claim.FencingToken,
		Attempt:        claim.Attempt,
		IdempotencyKey: claim.IdempotencyKey,
		LeaseExpiresAt: claim.LeaseExpiresAt,
	}
}

func projectRuntimeDurableSubtaskClaim(
	claim DurableSubtaskClaim,
) runruntime.DurableSubtaskClaim {
	return runruntime.DurableSubtaskClaim{
		RunID:          claim.RunID,
		TaskID:         claim.TaskID,
		ClaimID:        claim.ClaimID,
		ClaimOwner:     claim.ClaimOwner,
		InputDigest:    claim.InputDigest,
		FencingToken:   claim.FencingToken,
		Attempt:        claim.Attempt,
		IdempotencyKey: claim.IdempotencyKey,
		LeaseExpiresAt: claim.LeaseExpiresAt,
	}
}

func projectDurableSubtaskTerminal(
	receipt runruntime.DurableSubtaskTerminalReceipt,
) DurableSubtaskTerminalReceipt {
	return DurableSubtaskTerminalReceipt{
		ReceiptRef:        receipt.ReceiptRef,
		RunID:             receipt.RunID,
		TaskID:            receipt.TaskID,
		InputDigest:       receipt.InputDigest,
		Outcome:           DurableSubtaskOutcome(receipt.Outcome),
		Attempt:           receipt.Attempt,
		FencingToken:      receipt.FencingToken,
		IdempotencyKey:    receipt.IdempotencyKey,
		Summary:           receipt.Summary,
		FailureCode:       receipt.FailureCode,
		ResultArtifactRef: receipt.ResultArtifactRef,
		Payload:           cloneSubtaskPayload(receipt.Payload),
		CompletedAt:       receipt.CompletedAt,
	}
}
