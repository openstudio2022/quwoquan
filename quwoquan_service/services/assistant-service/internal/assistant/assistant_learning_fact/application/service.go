package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

var (
	ErrInvalid          = errors.New("assistant learning fact is invalid")
	ErrUnauthorized     = errors.New("assistant learning fact is unauthorized")
	ErrOwnerMismatch    = errors.New("assistant learning fact owner mismatch")
	ErrRunNotFound      = errors.New("assistant learning fact run not found")
	ErrIdentityConflict = errors.New("assistant learning fact identity conflict")
	ErrStoreUnavailable = errors.New("assistant learning fact store unavailable")
)

type Store interface {
	Append(context.Context, model.Fact) (model.Receipt, error)
}

type AppendKind string

const (
	AppendKindUserFeedback      AppendKind = "user_feedback"
	AppendKindTerminalScorecard AppendKind = "terminal_scorecard"
)

// AppendInput is the single typed application ingress for learning facts.
// User input must carry an authenticated context; terminal scorecards must not
// accept caller-supplied identity and derive their owner from the referenced run.
type AppendInput struct {
	Kind           AppendKind
	Command        model.AppendCommand
	TrustedContext *model.TrustedContext
}

// TerminalRunEvent is the object-owned application input consumed from the
// AssistantRun terminal lifecycle. It deliberately carries only the fields
// needed to append the canonical, non-training service scorecard.
type TerminalRunEvent struct {
	RunID      string
	DomainID   string
	Outcome    string
	OccurredAt time.Time
}

type AssistantLearningFactAppender struct {
	store     Store
	runOwners rundomain.OwnerReader
	now       func() time.Time
}

func NewAssistantLearningFactAppender(
	store Store,
	runOwners rundomain.OwnerReader,
	now func() time.Time,
) *AssistantLearningFactAppender {
	if now == nil {
		now = time.Now
	}
	return &AssistantLearningFactAppender{store: store, runOwners: runOwners, now: now}
}

func (service *AssistantLearningFactAppender) Append(
	ctx context.Context,
	input AppendInput,
) (model.Receipt, error) {
	command := input.Command
	switch input.Kind {
	case AppendKindUserFeedback:
		if input.TrustedContext == nil {
			return model.Receipt{}, fmt.Errorf(
				"%w: user feedback requires trusted identity",
				ErrUnauthorized,
			)
		}
		if command.FactType == model.FactTypeServiceScorecard {
			return model.Receipt{}, fmt.Errorf(
				"%w: public command cannot append service scorecard",
				ErrUnauthorized,
			)
		}
		owner, err := service.resolveRunOwner(ctx, command.AssistantTurnID)
		if err != nil {
			return model.Receipt{}, err
		}
		trusted := *input.TrustedContext
		if strings.TrimSpace(trusted.UserID) != owner.UserID ||
			strings.TrimSpace(trusted.PersonaID) != owner.PersonaID {
			return model.Receipt{}, ErrOwnerMismatch
		}
		if triggerMessageID := strings.TrimSpace(command.TriggerMessageID); triggerMessageID != "" &&
			triggerMessageID != owner.TriggerMessageID {
			return model.Receipt{}, fmt.Errorf(
				"%w: trigger message is not bound to assistant turn",
				ErrInvalid,
			)
		}
		return service.append(ctx, command, trusted, string(input.Kind))

	case AppendKindTerminalScorecard:
		if input.TrustedContext != nil {
			return model.Receipt{}, fmt.Errorf(
				"%w: terminal scorecard identity must be derived from the run",
				ErrUnauthorized,
			)
		}
		if command.FactType != model.FactTypeServiceScorecard {
			return model.Receipt{}, fmt.Errorf(
				"%w: terminal input only accepts service scorecards",
				ErrInvalid,
			)
		}
		owner, err := service.resolveRunOwner(ctx, command.AssistantTurnID)
		if err != nil {
			return model.Receipt{}, err
		}
		return service.append(ctx, command, model.TrustedContext{
			UserID:    owner.UserID,
			PersonaID: owner.PersonaID,
		}, string(input.Kind))

	default:
		return model.Receipt{}, fmt.Errorf(
			"%w: unknown append kind %q",
			ErrInvalid,
			input.Kind,
		)
	}
}

// AppendTerminalRun is the typed lifecycle-consumer use case used by the
// production terminal relay. The source event identity owns idempotency; a
// replay therefore returns the same durable learning-fact receipt.
func (service *AssistantLearningFactAppender) AppendTerminalRun(
	ctx context.Context,
	event TerminalRunEvent,
) (model.Receipt, error) {
	value := 0.0
	if strings.TrimSpace(event.Outcome) == "completed" {
		value = 1.0
	}
	return service.Append(ctx, AppendInput{
		Kind: AppendKindTerminalScorecard,
		Command: model.AppendCommand{
			EventID:          "turn:" + strings.TrimSpace(event.RunID) + ":completion",
			FactType:         model.FactTypeServiceScorecard,
			AssistantTurnID:  strings.TrimSpace(event.RunID),
			ReferralSource:   "service",
			DomainID:         strings.TrimSpace(event.DomainID),
			MetricID:         "turn_completion",
			MetricValue:      value,
			MetricSource:     "service_auto",
			TrainingEligible: false,
			OccurredAt:       event.OccurredAt,
		},
	})
}

func (service *AssistantLearningFactAppender) append(
	ctx context.Context,
	command model.AppendCommand,
	trusted model.TrustedContext,
	source string,
) (model.Receipt, error) {
	if service.store == nil {
		recordLearningFactAppend(source, string(command.FactType), "store_failed")
		return model.Receipt{}, ErrStoreUnavailable
	}
	fact, err := model.Build(command, trusted, service.now())
	if err != nil {
		recordLearningFactAppend(source, string(command.FactType), "rejected")
		return model.Receipt{}, fmt.Errorf("%w: %v", ErrInvalid, err)
	}
	receipt, err := service.store.Append(ctx, fact)
	if err != nil {
		recordLearningFactAppend(source, string(command.FactType), "store_failed")
		return model.Receipt{}, err
	}
	outcome := "accepted"
	if receipt.Deduplicated {
		outcome = "deduplicated"
	}
	recordLearningFactAppend(source, string(command.FactType), outcome)
	return receipt, nil
}

func (service *AssistantLearningFactAppender) resolveRunOwner(
	ctx context.Context,
	assistantTurnID string,
) (rundomain.Owner, error) {
	if service.runOwners == nil {
		return rundomain.Owner{}, ErrStoreUnavailable
	}
	owner, found, err := service.runOwners.ResolveRunOwner(
		ctx,
		strings.TrimSpace(assistantTurnID),
	)
	if err != nil {
		return rundomain.Owner{}, fmt.Errorf("%w: %v", ErrStoreUnavailable, err)
	}
	if !found {
		return rundomain.Owner{}, ErrRunNotFound
	}
	owner.UserID = strings.TrimSpace(owner.UserID)
	owner.PersonaID = strings.TrimSpace(owner.PersonaID)
	owner.TriggerMessageID = strings.TrimSpace(owner.TriggerMessageID)
	if owner.UserID == "" || owner.PersonaID == "" {
		return rundomain.Owner{}, fmt.Errorf(
			"%w: referenced run has no trusted owner",
			ErrStoreUnavailable,
		)
	}
	return owner, nil
}
