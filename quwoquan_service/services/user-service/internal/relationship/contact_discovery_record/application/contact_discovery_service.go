package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"

	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	contactgenerated "quwoquan_service/services/user-service/generated/relationship/contact_discovery_record"
	userevent "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/event"
	"quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	userrepo "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/ports"
)

const (
	discoveryRateLimit  = 5 // per owner per day
	discoveryBatchLimit = 5000
	discoveryTTLHours   = 72
)

// ContactDiscoveryService handles contact matching with privacy guarantees.
type ContactDiscoveryService struct {
	discoveries userrepo.ContactDiscoveryStore
	events      UserEventPublisher
}

type UserEventPublisher interface {
	PublishUserEvent(ctx context.Context, eventType, userID, actorID string, payload map[string]any) error
}

func NewContactDiscoveryService(
	discoveries userrepo.ContactDiscoveryStore,
	events UserEventPublisher,
) *ContactDiscoveryService {
	if discoveries == nil || events == nil {
		panic("contact discovery application requires store and event publisher")
	}
	return &ContactDiscoveryService{
		discoveries: discoveries,
		events:      events,
	}
}

// RunExpiredCleanup 周期性物理删除过期记录（含 hashed_phones），兑现
// metadata 声明的 72h TTL 隐私承诺。删除幂等，多实例并发安全。
func (s *ContactDiscoveryService) RunExpiredCleanup(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = time.Hour
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if deleted, err := s.discoveries.DeleteExpired(ctx); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "contact discovery expired cleanup failed", "err", err)
		} else if deleted > 0 {
			slog.InfoContext(ctx, "contact discovery expired records purged", "count", deleted)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// Initiate creates a discovery record and synchronously matches hashed phones.
// Privacy: returns only the record ID and status; caller fetches matches separately.
func (s *ContactDiscoveryService) Initiate(
	ctx context.Context,
	ownerID string,
	hashedPhones []string,
	idempotencyKey string,
) (*model.ContactDiscoveryRecord, error) {
	ownerID = strings.TrimSpace(ownerID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if ownerID == "" || idempotencyKey == "" || len(idempotencyKey) > 256 {
		return nil, usergenerated.AppErrorFromInvalidArgument(
			"owner and stable Idempotency-Key are required",
		)
	}
	if len(hashedPhones) > discoveryBatchLimit {
		return nil, contactgenerated.AppErrorFromTooManyContacts("too many contacts, maximum 5000 per request")
	}
	hashedPhones = normalizeHashedPhones(hashedPhones)

	record := &model.ContactDiscoveryRecord{
		ID:             uuid.New().String(),
		OwnerAccountID: ownerID,
		HashedPhones:   hashedPhones,
		Status:         "pending",
		ExpireAt:       time.Now().UTC().Add(discoveryTTLHours * time.Hour),
	}
	command := userrepo.CommandIdentity{
		Operation:      "InitiateContactDiscovery",
		OwnerAccountID: ownerID,
		IdempotencyKey: idempotencyKey,
		CommandDigest: contactCommandDigest(
			"InitiateContactDiscovery", ownerID, strings.Join(hashedPhones, ","),
		),
	}
	stored, created, err := s.discoveries.CreateIdempotent(
		ctx,
		record,
		discoveryRateLimit,
		command,
	)
	if errors.Is(err, userrepo.ErrRateLimited) {
		return nil, contactgenerated.AppErrorFromContactDiscoveryRateLimited(err.Error())
	}
	if errors.Is(err, userrepo.ErrIdempotencyConflict) {
		return nil, usergenerated.AppErrorFromInvalidArgument(err.Error())
	}
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("persist contact discovery command")
	}
	record = stored
	if !created && record.Status != "pending" {
		return record, nil
	}
	if created {
		_ = s.events.PublishUserEvent(ctx, userevent.ContactDiscoveryInitiated, ownerID, ownerID, map[string]any{
			"id":             record.ID,
			"ownerAccountId": ownerID,
			"createdAt":      time.Now().UTC().Format(time.RFC3339),
		})
	}

	// 同步匹配：批量哈希求交是一次索引查询（≤5000 哈希），P95 远低于
	// InitiateContactDiscovery 的 800ms SLO，无需异步作业。
	matches, err := s.discoveries.FindPhoneMatches(ctx, hashedPhones)
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError(
			"contact discovery dependency unavailable",
		)
	}
	matched := personaIDsFromMatches(matches)
	completed, transitioned, err := s.discoveries.CompleteIdempotent(
		ctx, record.ID, matched, command,
	)
	if err != nil {
		return nil, err
	}
	record = completed
	if transitioned {
		_ = s.events.PublishUserEvent(ctx, userevent.ContactDiscoveryCompleted, ownerID, ownerID, map[string]any{
			"id":             record.ID,
			"ownerAccountId": ownerID,
			"matchCount":     record.MatchCount,
			"completedAt":    time.Now().UTC().Format(time.RFC3339),
		})
	}

	return record, nil
}

// MatchesFor recomputes the enriched matches[] for an initiator's uploaded
// hashes (used to render GetLatest/Initiate responses). Relationship capability
// is layered on by the HTTP adapter, which owns the follow/block services.
func (s *ContactDiscoveryService) MatchesFor(ctx context.Context, hashedPhones []string) ([]model.ContactPhoneMatch, error) {
	if len(hashedPhones) == 0 {
		return []model.ContactPhoneMatch{}, nil
	}
	return s.discoveries.FindPhoneMatches(ctx, hashedPhones)
}

func personaIDsFromMatches(matches []model.ContactPhoneMatch) []string {
	ids := make([]string, 0, len(matches))
	for _, m := range matches {
		if m.PersonaID != "" {
			ids = append(ids, m.PersonaID)
		}
	}
	return ids
}

// GetLatest returns the latest discovery result for an owner.
// Privacy: never returns OwnerAccountID or HashedPhones.
func (s *ContactDiscoveryService) GetLatest(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error) {
	r, err := s.discoveries.FindLatestByOwner(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, nil
	}
	// Ensure expired records show as expired
	if r.ExpireAt.Before(time.Now().UTC()) && r.Status != "dismissed" {
		r.Status = "expired"
	}
	return r, nil
}

// Dismiss marks a discovery record as dismissed (user action).
func (s *ContactDiscoveryService) Dismiss(
	ctx context.Context,
	ownerID string,
	id string,
	idempotencyKey string,
) error {
	ownerID = strings.TrimSpace(ownerID)
	id = strings.TrimSpace(id)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if ownerID == "" || id == "" || idempotencyKey == "" || len(idempotencyKey) > 256 {
		return usergenerated.AppErrorFromInvalidArgument(
			"owner, discovery id and stable Idempotency-Key are required",
		)
	}
	err := s.discoveries.DismissIdempotent(
		ctx,
		id,
		userrepo.CommandIdentity{
			Operation:      "DismissContactDiscovery",
			OwnerAccountID: ownerID,
			IdempotencyKey: idempotencyKey,
			CommandDigest: contactCommandDigest(
				"DismissContactDiscovery", ownerID, id,
			),
		},
	)
	switch {
	case err == nil:
		return nil
	case errors.Is(err, userrepo.ErrNotFound):
		return contactgenerated.AppErrorFromContactDiscoveryNotFound(
			"discovery record not found",
		)
	case errors.Is(err, userrepo.ErrIdempotencyConflict):
		return usergenerated.AppErrorFromInvalidArgument(err.Error())
	default:
		return usergenerated.AppErrorFromInternalError("dismiss contact discovery")
	}
}

func normalizeHashedPhones(values []string) []string {
	unique := make(map[string]struct{}, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			unique[value] = struct{}{}
		}
	}
	result := make([]string, 0, len(unique))
	for value := range unique {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func contactCommandDigest(parts ...string) string {
	digest := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	return hex.EncodeToString(digest[:])
}
