package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	circleports "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/ports"
	generated "quwoquan_service/services/circle-service/generated/circle_management/circle"
)

const circleReceiptRetention = 24 * time.Hour

// CreateCircleCommand 是 CreateCircle 的 typed 输入（writable_fields 对齐
// services/circle-service/contracts/circle_management/circle/operations.yaml）。
type CreateCircleCommand struct {
	Name                string                                `json:"name"`
	Description         *string                               `json:"description"`
	RulesText           *string                               `json:"rulesText"`
	WelcomeMessage      *string                               `json:"welcomeMessage"`
	CoverUrl            *string                               `json:"coverUrl"`
	IconUrl             *string                               `json:"iconUrl"`
	Category            *string                               `json:"category"`
	SubCategory         *string                               `json:"subCategory"`
	Tags                []string                              `json:"tags"`
	Visibility          *circlemodel.CircleVisibility         `json:"visibility"`
	JoinPolicy          *circlemodel.CircleJoinPolicy         `json:"joinPolicy"`
	Kind                *circlemodel.CircleKind               `json:"kind"`
	DisplaySubjectType  *circlemodel.CircleDisplaySubjectType `json:"displaySubjectType"`
	FollowEnabled       *bool                                 `json:"followEnabled"`
	AutoSyncChat        *bool                                 `json:"autoSyncChat"`
	LinkedHomepageID    *string                               `json:"linkedHomepageId"`
	LinkedHomepageType  *circlemodel.HomepageType             `json:"linkedHomepageType"`
	LinkedHomepageTitle *string                               `json:"linkedHomepageTitle"`
}

// UpdateCircleCommand 是 UpdateCircle 的 typed PATCH 输入；nil 字段不修改。
type UpdateCircleCommand struct {
	CircleID            string                                `json:"-"`
	Name                *string                               `json:"name"`
	Description         *string                               `json:"description"`
	RulesText           *string                               `json:"rulesText"`
	WelcomeMessage      *string                               `json:"welcomeMessage"`
	CoverUrl            *string                               `json:"coverUrl"`
	IconUrl             *string                               `json:"iconUrl"`
	Category            *string                               `json:"category"`
	SubCategory         *string                               `json:"subCategory"`
	Tags                *[]string                             `json:"tags"`
	Visibility          *circlemodel.CircleVisibility         `json:"visibility"`
	JoinPolicy          *circlemodel.CircleJoinPolicy         `json:"joinPolicy"`
	Kind                *circlemodel.CircleKind               `json:"kind"`
	DisplaySubjectType  *circlemodel.CircleDisplaySubjectType `json:"displaySubjectType"`
	FollowEnabled       *bool                                 `json:"followEnabled"`
	AutoSyncChat        *bool                                 `json:"autoSyncChat"`
	LinkedHomepageID    *string                               `json:"linkedHomepageId"`
	LinkedHomepageType  *circlemodel.HomepageType             `json:"linkedHomepageType"`
	LinkedHomepageTitle *string                               `json:"linkedHomepageTitle"`
}

type UpdateCircleSectionsCommand struct {
	CircleID string
	Sections []circlemodel.CircleSectionConfig
}

// CircleCommandResult 对齐 fields.yaml CircleCommandResult。
type CircleCommandResult struct {
	CircleID         string                   `json:"circleId"`
	Version          int64                    `json:"version"`
	Status           circlemodel.CircleStatus `json:"status"`
	IdempotentReplay bool                     `json:"idempotentReplay"`
}

// CircleCommandFacade 承载 Circle 聚合本体的命名状态迁移：
// 服务端加载当前 version 内部 CAS + 有限重放；目标状态已满足时持久化
// no-op receipt；owner/admin 权限在提交前校验。
type CircleCommandFacade struct {
	store       circleports.AggregateStore
	memberships circleports.MembershipRoleReader
	cache       circleports.CacheInvalidator
	logger      *slog.Logger
	now         func() time.Time
}

func NewCircleCommandFacade(
	store circleports.AggregateStore,
	memberships circleports.MembershipRoleReader,
	cache circleports.CacheInvalidator,
	logger *slog.Logger,
) *CircleCommandFacade {
	if store == nil || memberships == nil {
		panic("CircleCommandFacade requires store and membership reader")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &CircleCommandFacade{
		store: store, memberships: memberships, cache: cache,
		logger: logger, now: time.Now,
	}
}

func (facade *CircleCommandFacade) Create(ctx context.Context, command CreateCircleCommand) (CircleCommandResult, error) {
	current, actorID, err := trustedCircleCommandContext(ctx)
	if err != nil {
		return CircleCommandResult{}, err
	}
	if strings.TrimSpace(command.Name) == "" {
		return CircleCommandResult{}, generated.AppErrorFromInvalidArgument("circle name is required")
	}
	name := command.Name
	change := circlemodel.ChangeSet{
		Kind:           circlemodel.ChangeCreate,
		CircleID:       stableCircleID(actorID, current.IdempotencyKey),
		OwnerPersonaID: actorID, Name: &name,
		Description: command.Description, RulesText: command.RulesText,
		WelcomeMessage: command.WelcomeMessage, CoverUrl: command.CoverUrl,
		IconUrl:  command.IconUrl,
		Category: command.Category, SubCategory: command.SubCategory,
		Tags: command.Tags, TagsSet: command.Tags != nil,
		Visibility: command.Visibility, JoinPolicy: command.JoinPolicy,
		Kind_: command.Kind, DisplaySubjectType: command.DisplaySubjectType,
		FollowEnabled: command.FollowEnabled, AutoSyncChat: command.AutoSyncChat,
		LinkedHomepageID: command.LinkedHomepageID, LinkedHomepageType: command.LinkedHomepageType,
		LinkedHomepageTitle: command.LinkedHomepageTitle,
		OccurredAt:          facade.now().UTC(),
	}
	return facade.commit(ctx, current, actorID, change)
}

func (facade *CircleCommandFacade) Update(ctx context.Context, command UpdateCircleCommand) (CircleCommandResult, error) {
	current, actorID, err := trustedCircleCommandContext(ctx)
	if err != nil {
		return CircleCommandResult{}, err
	}
	circle, err := facade.requireCircleAdmin(ctx, command.CircleID, actorID)
	if err != nil {
		return CircleCommandResult{}, err
	}
	change := circlemodel.ChangeSet{
		Kind: circlemodel.ChangeUpdate, CircleID: circle.ID,
		ExpectedVersion: circle.Version,
		Name:            command.Name, Description: command.Description,
		RulesText: command.RulesText, WelcomeMessage: command.WelcomeMessage,
		CoverUrl: command.CoverUrl, IconUrl: command.IconUrl,
		Category:    command.Category,
		SubCategory: command.SubCategory,
		Visibility:  command.Visibility, JoinPolicy: command.JoinPolicy,
		Kind_: command.Kind, DisplaySubjectType: command.DisplaySubjectType,
		FollowEnabled: command.FollowEnabled, AutoSyncChat: command.AutoSyncChat,
		LinkedHomepageID: command.LinkedHomepageID, LinkedHomepageType: command.LinkedHomepageType,
		LinkedHomepageTitle: command.LinkedHomepageTitle,
		OccurredAt:          facade.now().UTC(),
	}
	if command.Tags != nil {
		change.Tags, change.TagsSet = *command.Tags, true
	}
	return facade.commit(ctx, current, actorID, change)
}

func (facade *CircleCommandFacade) Archive(ctx context.Context, circleID string) (CircleCommandResult, error) {
	current, actorID, err := trustedCircleCommandContext(ctx)
	if err != nil {
		return CircleCommandResult{}, err
	}
	circle, err := facade.requireCircleOwner(ctx, circleID, actorID)
	if err != nil {
		return CircleCommandResult{}, err
	}
	change := circlemodel.ChangeSet{
		Kind: circlemodel.ChangeArchive, CircleID: circle.ID,
		ExpectedVersion: circle.Version, OccurredAt: facade.now().UTC(),
	}
	if circle.Status == circlemodel.CircleStatusArchived {
		return facade.recordNoop(ctx, current, actorID, circle, change)
	}
	return facade.commit(ctx, current, actorID, change)
}

func (facade *CircleCommandFacade) UpdateSections(ctx context.Context, command UpdateCircleSectionsCommand) (CircleCommandResult, error) {
	current, actorID, err := trustedCircleCommandContext(ctx)
	if err != nil {
		return CircleCommandResult{}, err
	}
	circle, err := facade.requireCircleAdmin(ctx, command.CircleID, actorID)
	if err != nil {
		return CircleCommandResult{}, err
	}
	change := circlemodel.ChangeSet{
		Kind: circlemodel.ChangeSections, CircleID: circle.ID,
		ExpectedVersion: circle.Version, Sections: command.Sections,
		OccurredAt: facade.now().UTC(),
	}
	return facade.commit(ctx, current, actorID, change)
}

func (facade *CircleCommandFacade) requireCircleOwner(ctx context.Context, circleID, actorID string) (circlemodel.Circle, error) {
	circle, found, err := facade.store.Load(ctx, strings.TrimSpace(circleID))
	if err != nil {
		return circlemodel.Circle{}, generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
	if !found {
		return circlemodel.Circle{}, generated.AppErrorFromCircleNotFound("circle not found")
	}
	if strings.TrimSpace(circle.OwnerID) != actorID {
		return circlemodel.Circle{}, generated.AppErrorFromPermissionDenied("circle owner role is required")
	}
	return circle, nil
}

func (facade *CircleCommandFacade) requireCircleAdmin(ctx context.Context, circleID, actorID string) (circlemodel.Circle, error) {
	circle, found, err := facade.store.Load(ctx, strings.TrimSpace(circleID))
	if err != nil {
		return circlemodel.Circle{}, generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
	if !found {
		return circlemodel.Circle{}, generated.AppErrorFromCircleNotFound("circle not found")
	}
	if strings.TrimSpace(circle.OwnerID) == actorID {
		return circle, nil
	}
	role, state, found, err := facade.memberships.ReadMembershipRole(ctx, circle.ID, actorID)
	if err != nil {
		return circlemodel.Circle{}, generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
	if !found || state != "active" || (role != "owner" && role != "admin") {
		return circlemodel.Circle{}, generated.AppErrorFromPermissionDenied("circle owner or admin role is required")
	}
	return circle, nil
}

func (facade *CircleCommandFacade) commit(ctx context.Context, current operation.Context, actorID string, change circlemodel.ChangeSet) (CircleCommandResult, error) {
	digest, err := circleCommandDigest(actorID, change)
	if err != nil {
		return CircleCommandResult{}, generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := facade.store.Commit(ctx, circleports.CommitRequest{
			Change:        change,
			ReceiptKey:    circleReceiptKey(actorID, current.IdempotencyKey),
			CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(circleReceiptRetention),
		})
		if commitErr == nil {
			facade.invalidateCache(ctx, receipt.CircleID)
			return CircleCommandResult{
				CircleID: receipt.CircleID, Version: receipt.Version,
				Status: receipt.Status, IdempotentReplay: receipt.Replayed,
			}, nil
		}
		if change.Kind == circlemodel.ChangeCreate ||
			!errors.Is(commitErr, circlemodel.ErrVersionConflict) ||
			attempt == 2 {
			return CircleCommandResult{}, mapCircleCommitError(commitErr)
		}
		latest, found, loadErr := facade.store.Load(ctx, change.CircleID)
		if loadErr != nil {
			return CircleCommandResult{}, generated.AppErrorFromCircleStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CircleCommandResult{}, generated.AppErrorFromCircleNotFound("circle vanished during retry")
		}
		if change.Kind == circlemodel.ChangeArchive && latest.Status == circlemodel.CircleStatusArchived {
			return facade.recordNoop(ctx, current, actorID, latest, change)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable Circle commit retry")
}

// recordNoop 持久化"目标状态已满足"回执：首个 Idempotency-Key 也能重放原始结果。
func (facade *CircleCommandFacade) recordNoop(ctx context.Context, current operation.Context, actorID string, circle circlemodel.Circle, change circlemodel.ChangeSet) (CircleCommandResult, error) {
	digest, err := circleCommandDigest(actorID, change)
	if err != nil {
		return CircleCommandResult{}, generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
	receipt, err := facade.store.RecordNoopReceipt(ctx, circleports.NoopReceipt{
		CircleID: circle.ID, Version: circle.Version, Status: circle.Status,
		ReceiptKey:    circleReceiptKey(actorID, current.IdempotencyKey),
		CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(circleReceiptRetention),
	})
	if err != nil {
		return CircleCommandResult{}, mapCircleCommitError(err)
	}
	return CircleCommandResult{
		CircleID: receipt.CircleID, Version: receipt.Version,
		Status: receipt.Status, IdempotentReplay: true,
	}, nil
}

func (facade *CircleCommandFacade) invalidateCache(ctx context.Context, circleID string) {
	if facade.cache == nil {
		return
	}
	if err := facade.cache.InvalidateCircle(ctx, circleID); err != nil {
		facade.logger.Warn("circle cache invalidation failed",
			"circleId", circleID, "error", err)
	}
}

func mapCircleCommitError(err error) error {
	switch {
	case errors.Is(err, circlemodel.ErrNotFound):
		return generated.AppErrorFromCircleNotFound(err.Error())
	case errors.Is(err, circlemodel.ErrArchived):
		return generated.AppErrorFromCircleArchived(err.Error())
	case errors.Is(err, circlemodel.ErrInvalidChange):
		return generated.AppErrorFromInvalidArgument(err.Error())
	case errors.Is(err, circlemodel.ErrVersionConflict):
		return generated.AppErrorFromCircleVersionConflict(err.Error())
	case errors.Is(err, circlemodel.ErrIdempotencyConflict):
		return generated.AppErrorFromCircleIdempotencyConflict(err.Error())
	default:
		return generated.AppErrorFromCircleStorageWriteFailed(err.Error())
	}
}

func trustedCircleCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func circleCommandDigest(actorID string, change circlemodel.ChangeSet) (string, error) {
	copied := change
	copied.OccurredAt = time.Time{}
	// 命名迁移的重放需要跨版本稳定的 digest：版本由服务端刷新，不入摘要。
	copied.ExpectedVersion = 0
	payload, err := json.Marshal(struct {
		ActorID string                `json:"actorId"`
		Change  circlemodel.ChangeSet `json:"change"`
	}{ActorID: actorID, Change: copied})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func circleReceiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "circle:" + hex.EncodeToString(sum[:])
}

func stableCircleID(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "c_" + hex.EncodeToString(sum[:16])
}
