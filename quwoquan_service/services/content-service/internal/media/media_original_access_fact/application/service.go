package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
	originalaccessports "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/ports"
)

// Decision is one already-made original media access outcome that must be
// audited. Every mutable input (grant deadline included) is decided by
// OriginalAccessQuota before it reaches this port.
type Decision struct {
	AssetID        string
	ViewerID       string
	Purpose        string
	Outcome        string
	Reason         string
	IdempotencyKey string
	CommandDigest  string
	DecidedAt      time.Time
	GrantExpiresAt time.Time
}

// Record is the immutable identity of one appended audit fact.
type Record struct {
	AuditID   string
	Outcome   string
	ExpiresAt time.Time
	Replayed  bool
}

// Service implements the MediaOriginalAccessAuditPort runtime entrypoint.
// It appends immutable decision facts and holds no instance-level mutable state.
type Service struct {
	store originalaccessports.Store
}

func NewService(store originalaccessports.Store) *Service {
	if store == nil {
		panic("MediaOriginalAccessFact audit port requires store")
	}
	return &Service{store: store}
}

func (service *Service) AppendAudit(ctx context.Context, decision Decision) (Record, error) {
	if strings.TrimSpace(decision.CommandDigest) == "" {
		return Record{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"审计事实缺少命令摘要",
			"media original access audit requires a command digest",
		)
	}
	fact := originalaccessmodel.Fact{
		AuditID:        auditID(decision),
		AssetID:        strings.TrimSpace(decision.AssetID),
		ViewerID:       strings.TrimSpace(decision.ViewerID),
		Purpose:        strings.ToLower(strings.TrimSpace(decision.Purpose)),
		Outcome:        strings.TrimSpace(decision.Outcome),
		Reason:         strings.TrimSpace(decision.Reason),
		IdempotencyKey: strings.TrimSpace(decision.IdempotencyKey),
		GrantedAt:      decision.DecidedAt.UTC(),
	}
	if fact.Outcome == "granted" {
		fact.ExpiresAt = decision.GrantExpiresAt.UTC()
	}
	appended, err := service.store.Append(ctx, originalaccessports.AppendRequest{
		Fact:          fact,
		CommandDigest: strings.TrimSpace(decision.CommandDigest),
	})
	if err != nil {
		return Record{}, Unavailable(err)
	}
	return Record{
		AuditID:   appended.Fact.AuditID,
		Outcome:   appended.Fact.Outcome,
		ExpiresAt: appended.Fact.ExpiresAt,
		Replayed:  appended.Replayed,
	}, nil
}

func auditID(decision Decision) string {
	digest := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(decision.IdempotencyKey),
		strings.TrimSpace(decision.AssetID),
		strings.TrimSpace(decision.ViewerID),
		strings.ToLower(strings.TrimSpace(decision.Purpose)),
		strings.TrimSpace(decision.Outcome),
		strings.TrimSpace(decision.Reason),
	}, ":")))
	return "moa_" + hex.EncodeToString(digest[:16])
}

// Unavailable normalizes infrastructure failures into the shared content
// dependency error while preserving already-typed AppErrors.
func Unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromRequiredDependencyUnavailable(err.Error())
}
