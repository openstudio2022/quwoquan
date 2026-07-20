// Package homepage_review 是 HomepageReview 对象专属 command/query facade。
// 命名状态迁移使用服务端内部 CAS + 有限重放；目标状态已满足时持久化 no-op receipt。
package homepage_review

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	reviewmodel "quwoquan_service/services/entity-service/internal/domain/homepage_review/model"
	reviewports "quwoquan_service/services/entity-service/internal/domain/homepage_review/ports"
	"quwoquan_service/services/entity-service/internal/generated"
)

const (
	reviewReceiptTTL = 24 * time.Hour

	EventReviewPublished = "HomepageReviewPublished"
	EventReviewUpdated   = "HomepageReviewUpdated"
	EventReviewRemoved   = "HomepageReviewRemoved"
)

// HomepageGate 是评价写入前的主页存在性窄读端口；由 Homepage 对象 Store 实现。
type HomepageGate interface {
	FindHomepageStatus(ctx context.Context, homepageID string) (status string, found bool, err error)
}

// SummaryProjector 在评价事实提交后推进 Homepage 侧摘要投影（最终一致，
// best-effort：失败由下一次写入或 outbox 重放收敛，不阻塞命令）。
type SummaryProjector interface {
	OnReviewCommitted(ctx context.Context, homepageID string)
}

type DataPorts struct {
	Aggregate reviewports.AggregateStore
	Page      reviewports.PageReader
	Homepage  HomepageGate
}

type Facade struct {
	data      DataPorts
	projector SummaryProjector
	now       func() time.Time
}

func NewFacade(data DataPorts) (*Facade, error) {
	if data.Aggregate == nil || data.Page == nil || data.Homepage == nil {
		return nil, errors.New("homepage review facade requires aggregate store, page reader and homepage gate")
	}
	return &Facade{data: data, now: time.Now}, nil
}

// WithSummaryProjector 装配摘要投影推进器（composition root 调用）。
func (f *Facade) WithSummaryProjector(projector SummaryProjector) *Facade {
	f.projector = projector
	return f
}

// SetClock 仅供测试注入确定性时钟。
func (f *Facade) SetClock(now func() time.Time) { f.now = now }

type CreateCommand struct {
	HomepageID                string
	ActorPersonaID            string
	Rating                    int
	Body                      string
	TagRefs                   []string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
}

type UpdateCommand struct {
	ReviewID                  string
	ActorPersonaID            string
	Rating                    int
	Body                      string
	TagRefs                   []string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
}

type DeleteCommand struct {
	ReviewID       string
	ActorPersonaID string
}

type ReviewView struct {
	ID                        string    `json:"id"`
	HomepageID                string    `json:"homepageId"`
	AuthorPersonaID           string    `json:"authorPersonaId"`
	AuthorDisplayNameSnapshot string    `json:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURLSnapshot   string    `json:"authorAvatarUrlSnapshot,omitempty"`
	Rating                    int       `json:"rating"`
	Body                      string    `json:"body,omitempty"`
	TagRefs                   []string  `json:"tagRefs,omitempty"`
	Status                    string    `json:"status"`
	Version                   int64     `json:"version"`
	CreatedAt                 time.Time `json:"createdAt"`
	UpdatedAt                 time.Time `json:"updatedAt"`
}

type ReviewPageSlice struct {
	Items      []ReviewView `json:"items"`
	NextCursor string       `json:"nextCursor,omitempty"`
}

func viewFromSnapshot(snapshot reviewmodel.Snapshot) ReviewView {
	return ReviewView{
		ID:                        snapshot.ID,
		HomepageID:                snapshot.HomepageID,
		AuthorPersonaID:           snapshot.AuthorPersonaID,
		AuthorDisplayNameSnapshot: snapshot.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   snapshot.AuthorAvatarURLSnapshot,
		Rating:                    snapshot.Rating,
		Body:                      snapshot.Body,
		TagRefs:                   snapshot.TagRefs,
		Status:                    string(snapshot.Status),
		Version:                   snapshot.Version,
		CreatedAt:                 snapshot.CreatedAt,
		UpdatedAt:                 snapshot.UpdatedAt,
	}
}

func viewFromAggregate(aggregate *reviewmodel.HomepageReview) ReviewView {
	return viewFromSnapshot(aggregate.Snapshot())
}

type reviewEventPayload struct {
	ID              string    `json:"reviewId"`
	HomepageID      string    `json:"homepageId"`
	AuthorPersonaID string    `json:"authorPersonaId,omitempty"`
	Rating          int       `json:"rating,omitempty"`
	TagRefs         []string  `json:"tagRefs,omitempty"`
	Status          string    `json:"status"`
	Version         int64     `json:"version"`
	CreatedAt       time.Time `json:"createdAt,omitempty"`
	UpdatedAt       time.Time `json:"updatedAt,omitempty"`
}

// Create 发表评价；软删记录上的再次创建复活同一聚合（版本继续推进）。
func (f *Facade) Create(ctx context.Context, command CreateCommand) (ReviewView, error) {
	actorID, err := requiredActor(command.ActorPersonaID)
	if err != nil {
		return ReviewView{}, err
	}
	command.ActorPersonaID = actorID
	digest, err := commandDigest("CreateHomepageReview", command)
	if err != nil {
		return ReviewView{}, err
	}
	if replayed, found, err := f.replay(ctx, actorID, "CreateHomepageReview", digest); err != nil || found {
		return replayed, err
	}
	homepageID := strings.TrimSpace(command.HomepageID)
	status, found, gateErr := f.data.Homepage.FindHomepageStatus(ctx, homepageID)
	if gateErr != nil {
		return ReviewView{}, unavailable(gateErr)
	}
	if !found {
		return ReviewView{}, generated.AppErrorFromHomepageNotFound(
			fmt.Sprintf("homepage %s not found for review", homepageID),
		)
	}
	if status == "offline" {
		return ReviewView{}, generated.AppErrorFromHomepageOffline(
			fmt.Sprintf("homepage %s is offline", homepageID),
		)
	}
	for attempt := 0; attempt < 3; attempt++ {
		existing, exists, loadErr := f.data.Aggregate.FindByAuthor(ctx, homepageID, actorID)
		if loadErr != nil {
			return ReviewView{}, unavailable(loadErr)
		}
		now := f.now().UTC()
		if !exists {
			aggregate, createErr := reviewmodel.Create(reviewmodel.CreateParams{
				ID:                        stableReviewID(homepageID, actorID),
				HomepageID:                homepageID,
				AuthorPersonaID:           actorID,
				AuthorDisplayNameSnapshot: command.AuthorDisplayNameSnapshot,
				AuthorAvatarURLSnapshot:   command.AuthorAvatarURLSnapshot,
				Rating:                    command.Rating,
				Body:                      command.Body,
				TagRefs:                   command.TagRefs,
				Now:                       now,
			})
			if createErr != nil {
				return ReviewView{}, mapDomainError(createErr)
			}
			result, commitErr := f.commit(
				ctx, actorID, aggregate, 0,
				"CreateHomepageReview", digest, EventReviewPublished, now,
			)
			if commitErr == nil {
				return result, nil
			}
			if !isVersionConflict(commitErr) || attempt == 2 {
				return ReviewView{}, commitErr
			}
			continue
		}
		if existing.Status() == reviewmodel.StatusActive {
			// 同一作者重复创建：内容一致视为 no-op，否则按更新语义拒绝，
			// 引导端侧走 UpdateHomepageReview。
			snapshot := existing.Snapshot()
			if snapshot.Rating == command.Rating &&
				snapshot.Body == strings.TrimSpace(command.Body) &&
				slices.Equal(snapshot.TagRefs, normalizeTagRefs(command.TagRefs)) {
				return f.recordNoop(ctx, actorID, existing, "CreateHomepageReview", digest)
			}
			return ReviewView{}, generated.AppErrorFromVersionConflict(
				"active review already exists; use UpdateHomepageReview",
			)
		}
		expected := existing.Version()
		if reviveErr := existing.Revive(actorID, reviewmodel.MutationParams{
			Rating:                    command.Rating,
			Body:                      command.Body,
			TagRefs:                   command.TagRefs,
			AuthorDisplayNameSnapshot: command.AuthorDisplayNameSnapshot,
			AuthorAvatarURLSnapshot:   command.AuthorAvatarURLSnapshot,
			Now:                       now,
		}); reviveErr != nil {
			return ReviewView{}, mapDomainError(reviveErr)
		}
		result, commitErr := f.commit(
			ctx, actorID, existing, expected,
			"CreateHomepageReview", digest, EventReviewPublished, now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return ReviewView{}, commitErr
		}
	}
	panic("unreachable homepage review create retry")
}

// Update 作者修改自己的评价；纯 CAS 冲突由服务端重载重放。
func (f *Facade) Update(ctx context.Context, command UpdateCommand) (ReviewView, error) {
	actorID, err := requiredActor(command.ActorPersonaID)
	if err != nil {
		return ReviewView{}, err
	}
	command.ActorPersonaID = actorID
	digest, err := commandDigest("UpdateHomepageReview", command)
	if err != nil {
		return ReviewView{}, err
	}
	if replayed, found, err := f.replay(ctx, actorID, "UpdateHomepageReview", digest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := f.data.Aggregate.Load(ctx, command.ReviewID)
		if loadErr != nil {
			return ReviewView{}, unavailable(loadErr)
		}
		if !found {
			return ReviewView{}, reviewNotFound(command.ReviewID)
		}
		snapshot := aggregate.Snapshot()
		if snapshot.Rating == command.Rating &&
			snapshot.Body == strings.TrimSpace(command.Body) &&
			slices.Equal(snapshot.TagRefs, normalizeTagRefs(command.TagRefs)) &&
			aggregate.Status() == reviewmodel.StatusActive {
			return f.recordNoop(ctx, actorID, aggregate, "UpdateHomepageReview", digest)
		}
		expected := aggregate.Version()
		now := f.now().UTC()
		if updateErr := aggregate.Update(actorID, reviewmodel.MutationParams{
			Rating:                    command.Rating,
			Body:                      command.Body,
			TagRefs:                   command.TagRefs,
			AuthorDisplayNameSnapshot: command.AuthorDisplayNameSnapshot,
			AuthorAvatarURLSnapshot:   command.AuthorAvatarURLSnapshot,
			Now:                       now,
		}); updateErr != nil {
			return ReviewView{}, mapDomainError(updateErr)
		}
		result, commitErr := f.commit(
			ctx, actorID, aggregate, expected,
			"UpdateHomepageReview", digest, EventReviewUpdated, now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return ReviewView{}, commitErr
		}
	}
	panic("unreachable homepage review update retry")
}

// Delete active -> deleted 命名迁移；目标状态已满足时持久化 no-op receipt。
func (f *Facade) Delete(ctx context.Context, command DeleteCommand) (ReviewView, error) {
	actorID, err := requiredActor(command.ActorPersonaID)
	if err != nil {
		return ReviewView{}, err
	}
	command.ActorPersonaID = actorID
	digest, err := commandDigest("DeleteHomepageReview", command)
	if err != nil {
		return ReviewView{}, err
	}
	if replayed, found, err := f.replay(ctx, actorID, "DeleteHomepageReview", digest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := f.data.Aggregate.Load(ctx, command.ReviewID)
		if loadErr != nil {
			return ReviewView{}, unavailable(loadErr)
		}
		if !found {
			return ReviewView{}, reviewNotFound(command.ReviewID)
		}
		if aggregate.Status() == reviewmodel.StatusDeleted {
			if strings.TrimSpace(aggregate.Snapshot().AuthorPersonaID) != actorID {
				return ReviewView{}, generated.AppErrorFromPermissionDenied(
					"only the author can delete this review",
				)
			}
			return f.recordNoop(ctx, actorID, aggregate, "DeleteHomepageReview", digest)
		}
		expected := aggregate.Version()
		now := f.now().UTC()
		if deleteErr := aggregate.Delete(actorID, now); deleteErr != nil {
			return ReviewView{}, mapDomainError(deleteErr)
		}
		result, commitErr := f.commit(
			ctx, actorID, aggregate, expected,
			"DeleteHomepageReview", digest, EventReviewRemoved, now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return ReviewView{}, commitErr
		}
	}
	panic("unreachable homepage review delete retry")
}

type ListQuery struct {
	HomepageID string
	Cursor     string
	Limit      int
}

func (f *Facade) ListByHomepage(ctx context.Context, query ListQuery) (ReviewPageSlice, error) {
	page, err := f.data.Page.ListByHomepage(
		ctx,
		strings.TrimSpace(query.HomepageID),
		reviewports.PageRequest{Cursor: strings.TrimSpace(query.Cursor), Limit: query.Limit},
	)
	if err != nil {
		return ReviewPageSlice{}, unavailable(err)
	}
	slice := ReviewPageSlice{NextCursor: page.NextCursor}
	for _, snapshot := range page.Items {
		slice.Items = append(slice.Items, viewFromSnapshot(snapshot))
	}
	if slice.Items == nil {
		slice.Items = []ReviewView{}
	}
	return slice, nil
}

// GetMine 返回当前 persona 的评价（active 或 deleted 均返回，供编辑/复活预填）。
func (f *Facade) GetMine(
	ctx context.Context,
	homepageID string,
	actorPersonaID string,
) (ReviewView, error) {
	actorID, err := requiredActor(actorPersonaID)
	if err != nil {
		return ReviewView{}, err
	}
	aggregate, found, loadErr := f.data.Aggregate.FindByAuthor(
		ctx,
		strings.TrimSpace(homepageID),
		actorID,
	)
	if loadErr != nil {
		return ReviewView{}, unavailable(loadErr)
	}
	if !found {
		return ReviewView{}, reviewNotFound("mine")
	}
	return viewFromAggregate(aggregate), nil
}

func (f *Facade) replay(
	ctx context.Context,
	actorID string,
	commandName string,
	digest string,
) (ReviewView, bool, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ReviewView{}, false, err
	}
	result, found, err := f.data.Aggregate.FindReceipt(ctx, idempotencyKey, commandName, digest)
	if err != nil {
		return ReviewView{}, false, unavailable(err)
	}
	if !found {
		return ReviewView{}, false, nil
	}
	if result.Aggregate == nil {
		return ReviewView{}, false, unavailable(errors.New("homepage review receipt has no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), true, nil
}

func (f *Facade) recordNoop(
	ctx context.Context,
	actorID string,
	aggregate *reviewmodel.HomepageReview,
	commandName string,
	digest string,
) (ReviewView, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ReviewView{}, err
	}
	result, err := f.data.Aggregate.RecordNoopReceipt(ctx, reviewports.NoopReceipt{
		Aggregate:        aggregate,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: f.now().UTC().Add(reviewReceiptTTL),
	})
	if err != nil {
		return ReviewView{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return ReviewView{}, unavailable(errors.New("homepage review no-op receipt returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), nil
}

func (f *Facade) commit(
	ctx context.Context,
	actorID string,
	aggregate *reviewmodel.HomepageReview,
	expectedVersion int64,
	commandName string,
	digest string,
	eventType string,
	now time.Time,
) (ReviewView, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ReviewView{}, err
	}
	snapshot := aggregate.Snapshot()
	payload, marshalErr := json.Marshal(reviewEventPayload{
		ID:              snapshot.ID,
		HomepageID:      snapshot.HomepageID,
		AuthorPersonaID: snapshot.AuthorPersonaID,
		Rating:          snapshot.Rating,
		TagRefs:         snapshot.TagRefs,
		Status:          string(snapshot.Status),
		Version:         snapshot.Version,
		CreatedAt:       snapshot.CreatedAt,
		UpdatedAt:       snapshot.UpdatedAt,
	})
	if marshalErr != nil {
		return ReviewView{}, unavailable(marshalErr)
	}
	result, commitErr := f.data.Aggregate.Commit(ctx, reviewports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.UTC().Add(reviewReceiptTTL),
		Events: []reviewports.OutboxEvent{{
			EventID:          eventIdentifier(idempotencyKey, eventType),
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       now.UTC(),
		}},
	})
	if commitErr != nil {
		return ReviewView{}, wrapCommitError(commitErr)
	}
	if result.Aggregate == nil {
		return ReviewView{}, unavailable(errors.New("homepage review commit returned no aggregate"))
	}
	if f.projector != nil && !result.Replayed {
		f.projector.OnReviewCommitted(ctx, snapshot.HomepageID)
	}
	return viewFromAggregate(result.Aggregate), nil
}

func requiredActor(raw string) (string, error) {
	actorID := strings.TrimSpace(raw)
	if actorID == "" {
		return "", generated.AppErrorFromPermissionDenied(
			"homepage review command requires an authenticated persona actor",
		)
	}
	return actorID, nil
}

func scopedIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	invocation, ok := operation.FromContext(ctx)
	rawKey := ""
	if ok {
		rawKey = strings.TrimSpace(invocation.IdempotencyKey)
	}
	if rawKey == "" {
		return "", generated.AppErrorFromInvalidArgument(
			"homepage review command requires Idempotency-Key",
		)
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "homepage-review:" + hex.EncodeToString(sum[:]), nil
}

// stableReviewID 由 homepageId+authorPersonaId 派生稳定 ID，
// 与唯一索引 (authorPersonaId, homepageId) 同构；复活复用同一文档。
func stableReviewID(homepageID, authorPersonaID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(homepageID) + "\x00" + strings.TrimSpace(authorPersonaID),
	))
	return "hpr_" + hex.EncodeToString(sum[:16])
}

func commandDigest(commandName string, command any) (string, error) {
	payload, err := json.Marshal(command)
	if err != nil {
		return "", unavailable(err)
	}
	sum := sha256.Sum256(append([]byte(commandName+"\x00"), payload...))
	return hex.EncodeToString(sum[:]), nil
}

func eventIdentifier(idempotencyKey, eventType string) string {
	sum := sha256.Sum256([]byte(idempotencyKey + "\x00" + eventType))
	return "hpr-event-" + hex.EncodeToString(sum[:16])
}

func normalizeTagRefs(tagRefs []string) []string {
	if len(tagRefs) == 0 {
		return nil
	}
	normalized := make([]string, 0, len(tagRefs))
	for _, tagRef := range tagRefs {
		trimmed := strings.TrimSpace(tagRef)
		if trimmed == "" {
			continue
		}
		normalized = append(normalized, trimmed)
	}
	if len(normalized) == 0 {
		return nil
	}
	return normalized
}

func reviewNotFound(reviewID string) error {
	return generated.AppErrorFromReviewNotFound(
		fmt.Sprintf("homepage review %s not found", reviewID),
	)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, reviewmodel.ErrReviewForbidden):
		return generated.AppErrorFromPermissionDenied(err.Error())
	case errors.Is(err, reviewmodel.ErrInvalidRating),
		errors.Is(err, reviewmodel.ErrInvalidReview):
		return generated.AppErrorFromInvalidArgument(err.Error())
	case errors.Is(err, reviewmodel.ErrReviewDeleted):
		return generated.AppErrorFromReviewNotFound(err.Error())
	default:
		return unavailable(err)
	}
}

func isVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == generated.ErrVersionConflict.Error()
}

func wrapCommitError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return generated.AppErrorFromInternalError(err.Error())
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return generated.AppErrorFromInternalError(err.Error())
}
