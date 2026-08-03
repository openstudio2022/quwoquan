package application

import (
	"context"
	"errors"

	closuremodel "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/domain/model"
)

type ApplyResult struct {
	Replayed bool
}

type Processor interface {
	Apply(context.Context, closuremodel.UserAccountClosedEvent) (ApplyResult, error)
}

type Ingress struct {
	processor Processor
}

func NewIngress(processor Processor) *Ingress {
	if processor == nil {
		panic("ContentAccountClosureWorkflow ingress requires processor")
	}
	return &Ingress{processor: processor}
}

func (ingress *Ingress) Apply(
	ctx context.Context,
	event closuremodel.UserAccountClosedEvent,
) (ApplyResult, error) {
	if ingress == nil || ingress.processor == nil {
		return ApplyResult{}, errors.New("ContentAccountClosureWorkflow ingress is unavailable")
	}
	if err := event.Validate(); err != nil {
		return ApplyResult{}, err
	}
	return ingress.processor.Apply(ctx, event)
}
