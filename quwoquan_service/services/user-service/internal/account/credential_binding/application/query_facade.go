package credential_binding

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/user-service/generated/account/user_account"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

type CredentialView struct {
	ID             string    `json:"id"`
	CredentialType string    `json:"credentialType"`
	DisplayLabel   string    `json:"displayLabel,omitempty"`
	IsActive       bool      `json:"isActive"`
	BoundAt        time.Time `json:"boundAt"`
	Version        int64     `json:"version"`
}

type CredentialQueryFacade struct {
	store bindingports.AggregateStore
}

func NewCredentialQueryFacade(
	store bindingports.AggregateStore,
) *CredentialQueryFacade {
	if store == nil {
		panic("CredentialQueryFacade requires an object-specific AggregateStore")
	}
	return &CredentialQueryFacade{store: store}
}

func (facade *CredentialQueryFacade) ListCredentials(
	ctx context.Context,
) ([]CredentialView, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorAccount) != nil {
		return nil, generated.AppErrorFromUnauthorized(
			"CredentialBinding query requires a trusted account actor",
		)
	}
	ownerID := strings.TrimSpace(current.Actor.AccountID)
	items, err := facade.store.ListByOwner(ctx, ownerID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"CredentialBinding query failed",
		)
	}
	result := make([]CredentialView, 0, len(items))
	for _, item := range items {
		snapshot := item.Snapshot()
		if snapshot.Status != bindingmodel.StatusActive {
			continue
		}
		result = append(result, CredentialView{
			ID:             snapshot.ID,
			CredentialType: string(snapshot.CredentialType),
			DisplayLabel:   snapshot.DisplayLabel,
			IsActive:       true,
			BoundAt:        snapshot.BoundAt.UTC(),
			Version:        snapshot.Version,
		})
	}
	return result, nil
}
