package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

const sessionKeyPrefix = "integration:capability-grant:"

type RedisSessionStore struct {
	client rtredis.Client
}

func NewRedisSessionStore(client rtredis.Client) (*RedisSessionStore, error) {
	if client == nil {
		return nil, errors.New("capability grant Redis client is required")
	}
	return &RedisSessionStore{client: client}, nil
}

type persistedSession struct {
	ResolutionID       string                 `json:"resolutionId"`
	AccountDigest      string                 `json:"accountDigest"`
	ServiceActorDigest string                 `json:"serviceActorDigest"`
	CapabilityKey      string                 `json:"capabilityKey"`
	SurfaceKind        string                 `json:"surfaceKind"`
	BindingKind        grantmodel.BindingKind `json:"bindingKind"`
	BindingDigest      string                 `json:"bindingDigest"`
	InputDigest        string                 `json:"inputDigest"`
	ConfirmationDigest string                 `json:"confirmationDigest"`
	PermitDigest       string                 `json:"permitDigest"`
	IdempotencyDigest  string                 `json:"idempotencyDigest"`
	ResolvedAt         time.Time              `json:"resolvedAt"`
	ExpiresAt          time.Time              `json:"expiresAt"`
}

func (store *RedisSessionStore) Save(
	ctx context.Context,
	grant grantmodel.ResolvedCapabilityGrant,
) error {
	if store == nil || store.client == nil || ctx == nil ||
		strings.TrimSpace(grant.ResolutionID) == "" ||
		strings.TrimSpace(grant.CapabilityKey) == "" ||
		grant.ResolvedAt.IsZero() || grant.ExpiresAt == nil ||
		!grant.ExpiresAt.Equal(grant.ResolvedAt.Add(grantmodel.GrantTTL)) {
		return grantmodel.ErrInvalidResolvedGrant
	}
	finalDigests := []string{
		grant.InputDigest,
		grant.ConfirmationDigest,
		grant.PermitDigest,
		grant.IdempotencyDigest,
	}
	if grant.InputDigest == "" {
		if grant.ServiceActorDigest != "" || grant.ConfirmationDigest != "" ||
			grant.PermitDigest != "" || grant.IdempotencyDigest != "" {
			return grantmodel.ErrInvalidResolvedGrant
		}
	} else {
		if !grantmodel.IsValidDigest(grant.ServiceActorDigest) {
			return grantmodel.ErrInvalidResolvedGrant
		}
		for _, digest := range finalDigests {
			if !grantmodel.IsValidDigest(digest) {
				return grantmodel.ErrInvalidResolvedGrant
			}
		}
	}
	bindingDigest, err := grantmodel.BindingDigest(grant)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(persistedSession{
		ResolutionID:       strings.TrimSpace(grant.ResolutionID),
		AccountDigest:      grantmodel.OpaqueDigest(grant.AccountID),
		ServiceActorDigest: strings.TrimSpace(grant.ServiceActorDigest),
		CapabilityKey:      strings.TrimSpace(grant.CapabilityKey),
		SurfaceKind:        strings.TrimSpace(grant.SurfaceKind),
		BindingKind:        grant.BindingKind,
		BindingDigest:      bindingDigest,
		InputDigest:        strings.TrimSpace(grant.InputDigest),
		ConfirmationDigest: strings.TrimSpace(grant.ConfirmationDigest),
		PermitDigest:       strings.TrimSpace(grant.PermitDigest),
		IdempotencyDigest:  strings.TrimSpace(grant.IdempotencyDigest),
		ResolvedAt:         grant.ResolvedAt.UTC(),
		ExpiresAt:          grant.ExpiresAt.UTC(),
	})
	if err != nil {
		return err
	}
	key := sessionKeyPrefix + strings.TrimSpace(grant.ResolutionID)
	created, err := store.client.SetNX(
		ctx,
		key,
		string(payload),
		grantmodel.GrantTTL,
	)
	if err != nil {
		return err
	}
	if created {
		return nil
	}
	existing, err := store.client.GetBytes(ctx, key)
	if err != nil {
		return err
	}
	if string(existing) != string(payload) {
		return grantmodel.ErrInvalidResolvedGrant
	}
	// Idempotent replay never calls EXPIRE or SET again: the original 300s
	// session deadline is immutable and cannot be renewed by read/save replay.
	return nil
}

func (store *RedisSessionStore) Load(
	ctx context.Context,
	resolutionID string,
) (grantapp.StoredSession, error) {
	resolutionID = strings.TrimSpace(resolutionID)
	if store == nil || store.client == nil || ctx == nil || resolutionID == "" {
		return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
	}
	payload, err := store.client.GetBytes(ctx, sessionKeyPrefix+resolutionID)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return grantapp.StoredSession{}, grantapp.ErrCapabilityGrantSessionNotFound
	}
	if err != nil {
		return grantapp.StoredSession{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var persisted persistedSession
	if err := decoder.Decode(&persisted); err != nil {
		return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
	}
	if persisted.ResolutionID != resolutionID ||
		!grantmodel.IsValidDigest(persisted.AccountDigest) ||
		strings.TrimSpace(persisted.CapabilityKey) == "" ||
		!grantmodel.IsValidBindingKind(persisted.BindingKind) ||
		!grantmodel.IsValidDigest(persisted.BindingDigest) ||
		persisted.ResolvedAt.IsZero() || persisted.ExpiresAt.IsZero() ||
		!persisted.ExpiresAt.Equal(persisted.ResolvedAt.Add(grantmodel.GrantTTL)) {
		return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
	}
	if persisted.ServiceActorDigest != "" &&
		!grantmodel.IsValidDigest(persisted.ServiceActorDigest) {
		return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
	}
	for _, digest := range []string{
		persisted.InputDigest,
		persisted.ConfirmationDigest,
		persisted.PermitDigest,
		persisted.IdempotencyDigest,
	} {
		if digest != "" && !grantmodel.IsValidDigest(digest) {
			return grantapp.StoredSession{}, grantmodel.ErrInvalidResolvedGrant
		}
	}
	return grantapp.StoredSession{
		ResolutionID:       persisted.ResolutionID,
		AccountDigest:      persisted.AccountDigest,
		ServiceActorDigest: persisted.ServiceActorDigest,
		CapabilityKey:      persisted.CapabilityKey,
		SurfaceKind:        persisted.SurfaceKind,
		BindingKind:        persisted.BindingKind,
		BindingDigest:      persisted.BindingDigest,
		InputDigest:        persisted.InputDigest,
		ConfirmationDigest: persisted.ConfirmationDigest,
		PermitDigest:       persisted.PermitDigest,
		IdempotencyDigest:  persisted.IdempotencyDigest,
		ResolvedAt:         persisted.ResolvedAt.UTC(),
		ExpiresAt:          persisted.ExpiresAt.UTC(),
	}, nil
}

var _ grantapp.SessionStore = (*RedisSessionStore)(nil)
