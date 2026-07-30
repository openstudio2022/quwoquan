package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

const (
	OperationOpenModeration = "open_moderation"
	OperationOpenAppeal     = "open_appeal"
	OperationReview         = "review"
	OperationRetryDelivery  = "retry_delivery"
)

type OpenModerationCommand struct {
	CaseID         string
	AccountID      string
	PolicyRef      string
	EvidenceRefs   []string
	ActorID        string
	IdempotencyKey string
}

type OpenAppealCommand struct {
	CaseID           string
	AccountID        string
	SourceDecisionID string
	IntakeRef        string
	EvidenceRefs     []string
	ActorID          string
	IdempotencyKey   string
}

type ReviewCommand struct {
	CaseID         string
	Verdict        model.ReviewVerdict
	ActorID        string
	IdempotencyKey string
}

type RetryDeliveryCommand struct {
	CaseID         string
	ActorID        string
	IdempotencyKey string
}

type Result struct {
	CaseID           string               `json:"caseId"`
	CaseKind         model.CaseKind       `json:"caseKind"`
	Status           model.CaseStatus     `json:"status"`
	Version          int64                `json:"version"`
	ApprovalCount    int                  `json:"approvalCount"`
	DecisionID       string               `json:"decisionId,omitempty"`
	DeliveryStatus   model.DeliveryStatus `json:"deliveryStatus,omitempty"`
	UpdatedAt        time.Time            `json:"updatedAt"`
	IdempotentReplay bool                 `json:"-"`
}

type Service struct {
	store         ports.CaseStore
	appealIntakes ports.AppealIntakeVerifier
	metrics       ports.Metrics
	now           func() time.Time
}

func NewService(
	store ports.CaseStore,
	metrics ports.Metrics,
	appealIntakes ports.AppealIntakeVerifier,
) *Service {
	if store == nil {
		panic("AccountEnforcementCase service requires a store")
	}
	if metrics == nil {
		metrics = noopMetrics{}
	}
	return &Service{
		store: store, appealIntakes: appealIntakes, metrics: metrics, now: time.Now,
	}
}

func (service *Service) OpenModeration(
	ctx context.Context,
	command OpenModerationCommand,
) (Result, error) {
	started := time.Now()
	outcome := "failed"
	defer func() {
		service.metrics.ObserveCaseCommand(OperationOpenModeration, outcome, time.Since(started))
	}()
	idempotencyKey, ok := normalizeOpaque(command.IdempotencyKey, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.IdempotencyKey = idempotencyKey
	now := service.now().UTC()
	current, err := model.OpenModeration(model.OpenModerationParams{
		CaseID:       command.CaseID,
		AccountID:    command.AccountID,
		PolicyRef:    command.PolicyRef,
		EvidenceRefs: command.EvidenceRefs,
		OpenedBy:     command.ActorID,
		OpenedAt:     now,
	})
	if err != nil {
		return Result{}, model.ErrInvalidArgument
	}
	commandDigest := stableDigest(struct {
		Operation   string `json:"operation"`
		ActorID     string `json:"actorId"`
		Fingerprint string `json:"fingerprint"`
	}{Operation: OperationOpenModeration, ActorID: current.OpenedBy, Fingerprint: current.Fingerprint()})
	if replay, found, replayErr := service.store.Replay(ctx, command.IdempotencyKey, commandDigest); replayErr != nil {
		return Result{}, replayErr
	} else if found {
		outcome = "replayed"
		return resultFromSnapshot(replay), nil
	}
	snapshot, err := service.store.CommitOpen(ctx, current, ports.CommandReceipt{
		IdempotencyKey: command.IdempotencyKey,
		CommandDigest:  commandDigest,
		CaseID:         current.ID,
		ResultVersion:  current.Version,
		CreatedAt:      now,
	})
	if err != nil {
		return Result{}, err
	}
	if snapshot.IdempotentReplay {
		outcome = "replayed"
	} else {
		outcome = "committed"
	}
	return resultFromSnapshot(snapshot), nil
}

func (service *Service) claimAppealIntake(
	ctx context.Context,
	current model.Case,
) error {
	if service.appealIntakes == nil {
		return ports.ErrAppealIntakeUnavailable
	}
	err := service.appealIntakes.Claim(ctx, ports.AppealIntakeClaim{
		IntakeRef: current.IntakeRef,
		AccountID: current.AccountID,
		CaseID:    current.ID,
	})
	switch {
	case err == nil:
		return nil
	case errors.Is(err, ports.ErrAppealIntakeInvalid),
		errors.Is(err, ports.ErrAppealIntakeAccountMismatch),
		errors.Is(err, ports.ErrAppealIntakeConsumed):
		return model.ErrSourceDecisionConflict
	case errors.Is(err, ports.ErrAppealIntakeUnavailable):
		return err
	default:
		return fmt.Errorf("%w: claim failed", ports.ErrAppealIntakeUnavailable)
	}
}

func (service *Service) OpenAppeal(
	ctx context.Context,
	command OpenAppealCommand,
) (Result, error) {
	started := time.Now()
	outcome := "failed"
	defer func() {
		service.metrics.ObserveCaseCommand(OperationOpenAppeal, outcome, time.Since(started))
	}()
	idempotencyKey, ok := normalizeOpaque(command.IdempotencyKey, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.IdempotencyKey = idempotencyKey
	now := service.now().UTC()
	current, err := model.OpenAppeal(model.OpenAppealParams{
		CaseID:           command.CaseID,
		AccountID:        command.AccountID,
		SourceDecisionID: command.SourceDecisionID,
		IntakeRef:        command.IntakeRef,
		EvidenceRefs:     command.EvidenceRefs,
		OpenedBy:         command.ActorID,
		OpenedAt:         now,
	})
	if err != nil {
		return Result{}, model.ErrInvalidArgument
	}
	commandDigest := stableDigest(struct {
		Operation   string `json:"operation"`
		ActorID     string `json:"actorId"`
		Fingerprint string `json:"fingerprint"`
	}{Operation: OperationOpenAppeal, ActorID: current.OpenedBy, Fingerprint: current.Fingerprint()})
	if replay, found, replayErr := service.store.Replay(ctx, command.IdempotencyKey, commandDigest); replayErr != nil {
		return Result{}, replayErr
	} else if found {
		outcome = "replayed"
		return resultFromSnapshot(replay), nil
	}
	if err := service.claimAppealIntake(ctx, current); err != nil {
		return Result{}, err
	}
	snapshot, err := service.store.CommitOpen(ctx, current, ports.CommandReceipt{
		IdempotencyKey: command.IdempotencyKey,
		CommandDigest:  commandDigest,
		CaseID:         current.ID,
		ResultVersion:  current.Version,
		CreatedAt:      now,
	})
	if err != nil {
		return Result{}, err
	}
	if snapshot.IdempotentReplay {
		outcome = "replayed"
	} else {
		outcome = "committed"
	}
	return resultFromSnapshot(snapshot), nil
}

func (service *Service) Review(
	ctx context.Context,
	command ReviewCommand,
) (Result, error) {
	started := time.Now()
	outcome := "failed"
	defer func() {
		service.metrics.ObserveCaseCommand(OperationReview, outcome, time.Since(started))
	}()
	var ok bool
	command.CaseID, ok = normalizeOpaque(command.CaseID, 128)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.ActorID, ok = normalizeOpaque(command.ActorID, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.IdempotencyKey, ok = normalizeOpaque(command.IdempotencyKey, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	commandDigest := stableDigest(struct {
		Operation string `json:"operation"`
		CaseID    string `json:"caseId"`
		ActorID   string `json:"actorId"`
		Verdict   string `json:"verdict"`
	}{OperationReview, command.CaseID, command.ActorID, string(command.Verdict)})
	if replay, found, replayErr := service.store.Replay(ctx, command.IdempotencyKey, commandDigest); replayErr != nil {
		return Result{}, replayErr
	} else if found {
		outcome = "replayed"
		return resultFromSnapshot(replay), nil
	}
	var snapshot ports.CaseSnapshot
	for attempt := 0; attempt < 3; attempt++ {
		current, err := service.store.Load(ctx, command.CaseID)
		if err != nil {
			return Result{}, err
		}
		now := service.now().UTC()
		next, review, decision, err := current.Review(command.ActorID, command.Verdict, now)
		if err != nil {
			return Result{}, err
		}
		snapshot, err = service.store.CommitReview(
			ctx,
			current.Version,
			next,
			review,
			decision,
			ports.CommandReceipt{
				IdempotencyKey: command.IdempotencyKey,
				CommandDigest:  commandDigest,
				CaseID:         next.ID,
				ResultVersion:  next.Version,
				CreatedAt:      now,
			},
		)
		if err == nil {
			break
		}
		if !errors.Is(err, model.ErrVersionConflict) || attempt == 2 {
			return Result{}, err
		}
	}
	if snapshot.IdempotentReplay {
		outcome = "replayed"
	} else {
		outcome = "committed"
	}
	return resultFromSnapshot(snapshot), nil
}

func (service *Service) RetryDelivery(
	ctx context.Context,
	command RetryDeliveryCommand,
) (Result, error) {
	started := time.Now()
	outcome := "failed"
	defer func() {
		service.metrics.ObserveCaseCommand(OperationRetryDelivery, outcome, time.Since(started))
	}()
	var ok bool
	command.CaseID, ok = normalizeOpaque(command.CaseID, 128)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.ActorID, ok = normalizeOpaque(command.ActorID, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	command.IdempotencyKey, ok = normalizeOpaque(command.IdempotencyKey, 160)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	commandDigest := stableDigest(struct {
		Operation string `json:"operation"`
		CaseID    string `json:"caseId"`
		ActorID   string `json:"actorId"`
	}{OperationRetryDelivery, command.CaseID, command.ActorID})
	if replay, found, replayErr := service.store.Replay(ctx, command.IdempotencyKey, commandDigest); replayErr != nil {
		return Result{}, replayErr
	} else if found {
		outcome = "replayed"
		return resultFromSnapshot(replay), nil
	}
	now := service.now().UTC()
	snapshot, err := service.store.RecoverDelivery(ctx, command.CaseID, ports.CommandReceipt{
		IdempotencyKey: command.IdempotencyKey,
		CommandDigest:  commandDigest,
		CaseID:         command.CaseID,
		CreatedAt:      now,
	}, now)
	if err != nil {
		return Result{}, err
	}
	if snapshot.IdempotentReplay {
		outcome = "replayed"
	} else {
		outcome = "committed"
	}
	return resultFromSnapshot(snapshot), nil
}

func (service *Service) Get(ctx context.Context, caseID string) (Result, error) {
	var ok bool
	caseID, ok = normalizeOpaque(caseID, 128)
	if !ok {
		return Result{}, model.ErrInvalidArgument
	}
	current, err := service.store.Load(ctx, caseID)
	if err != nil {
		return Result{}, err
	}
	return resultFromSnapshot(ports.CaseSnapshot{Case: current}), nil
}

func resultFromSnapshot(snapshot ports.CaseSnapshot) Result {
	if snapshot.CommandResult != nil {
		stored := snapshot.CommandResult
		return Result{
			CaseID:           stored.CaseID,
			CaseKind:         stored.CaseKind,
			Status:           stored.Status,
			Version:          stored.Version,
			ApprovalCount:    stored.ApprovalCount,
			DecisionID:       stored.DecisionID,
			DeliveryStatus:   stored.DeliveryStatus,
			UpdatedAt:        stored.UpdatedAt.UTC(),
			IdempotentReplay: snapshot.IdempotentReplay,
		}
	}
	current := snapshot.Case
	result := Result{
		CaseID:           current.ID,
		CaseKind:         current.Kind,
		Status:           current.Status,
		Version:          current.Version,
		DeliveryStatus:   current.DeliveryStatus,
		UpdatedAt:        current.UpdatedAt.UTC(),
		IdempotentReplay: snapshot.IdempotentReplay,
	}
	for _, review := range current.Reviews {
		if review.Verdict == model.ReviewVerdictApprove {
			result.ApprovalCount++
		}
	}
	if current.Decision != nil {
		result.DecisionID = current.Decision.ID
	}
	return result
}

func normalizeOpaque(value string, max int) (string, bool) {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > max {
		return "", false
	}
	for _, current := range value {
		if current < 0x20 || current == 0x7f {
			return "", false
		}
	}
	return value, true
}

func stableDigest(value any) string {
	payload, _ := json.Marshal(value)
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

type noopMetrics struct{}

func (noopMetrics) ObserveCaseCommand(string, string, time.Duration) {}
func (noopMetrics) ObserveDelivery(string, string, time.Duration)    {}
func (noopMetrics) SetDeliveryBacklog(string, float64)               {}

var _ ports.Metrics = noopMetrics{}
