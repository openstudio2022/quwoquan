package application

import (
	"context"
	"errors"
	"strings"
)

type Command struct {
	DeliveryID string
	AccountID  string
	Title      string
	Body       string
	DeepLink   string
}

type Receipt struct {
	DeliveryID string
	ProviderID string
	Accepted   bool
}

type ProviderPort interface {
	Deliver(context.Context, Command) (Receipt, error)
}

type Facade struct{ provider ProviderPort }

func NewFacade(provider ProviderPort) *Facade { return &Facade{provider: provider} }

func (f *Facade) Deliver(ctx context.Context, command Command) (Receipt, error) {
	if f == nil || f.provider == nil {
		return Receipt{}, errors.New("push delivery provider is unavailable")
	}
	if strings.TrimSpace(command.DeliveryID) == "" || strings.TrimSpace(command.AccountID) == "" || strings.TrimSpace(command.Body) == "" {
		return Receipt{}, errors.New("push delivery identity, accountId and body are required")
	}
	return f.provider.Deliver(ctx, command)
}
