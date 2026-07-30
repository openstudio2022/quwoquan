// Package homepage_claim_request 实现 HomepageClaimRequest 对象专属 Facade。
package homepage_claim_request

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	claimgenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage_claim_request"
	claimmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/model"
	claimports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/ports"
)

const (
	receiptTTL = 24 * time.Hour

	EventClaimRequested = "HomepageClaimRequested"
	EventClaimReviewed  = "HomepageClaimReviewed"
)

type HomepageState struct {
	Status      string
	ClaimStatus string
}

// HomepageGate 是认领申请创建前的跨对象窄读端口。
type HomepageGate interface {
	FindHomepageState(ctx context.Context, homepageID string) (HomepageState, bool, error)
}

type DataPorts struct {
	Aggregates claimports.AggregateStore
	Receipts   claimports.ReceiptStore
	Homepages  HomepageGate
	Queue      claimports.QueueReader
}

type Facade struct {
	data  DataPorts
	now   func() time.Time
	newID func() string
}

func NewFacade(data DataPorts) (*Facade, error) {
	if data.Aggregates == nil || data.Receipts == nil || data.Homepages == nil || data.Queue == nil {
		return nil, errors.New(
			"homepage claim request facade requires aggregate, receipt, homepage and queue reader ports",
		)
	}
	return &Facade{
		data: data,
		now:  time.Now,
		newID: func() string {
			return "hcr_" + uuid.NewString()
		},
	}, nil
}

// SetClock 仅用于确定性测试。
func (f *Facade) SetClock(now func() time.Time) {
	if now != nil {
		f.now = now
	}
}

// SetIDGenerator 仅用于确定性测试；生产默认使用 UUID。
func (f *Facade) SetIDGenerator(generator func() string) {
	if generator != nil {
		f.newID = generator
	}
}

type CreateCommand struct {
	HomepageID           string
	ActorPersonaID       string
	ClaimTier            claimmodel.ClaimTier
	BusinessLicenseURL   string
	ContactPhone         string
	IdentityCardFrontURL string
	IdentityCardBackURL  string
	Note                 string
}

type ReviewCommand struct {
	HomepageID     string
	ClaimRequestID string
	ActorAccountID string
	TargetStatus   claimmodel.Status
	ReviewNote     string
}

type ClaimRequestView struct {
	ClaimRequestID       string               `json:"claimRequestId"`
	Version              int64                `json:"version"`
	HomepageID           string               `json:"homepageId"`
	RequesterPersonaID   string               `json:"requesterPersonaId"`
	ClaimTier            claimmodel.ClaimTier `json:"claimTier"`
	BusinessLicenseURL   string               `json:"businessLicenseUrl,omitempty"`
	ContactPhone         string               `json:"contactPhone,omitempty"`
	IdentityCardFrontURL string               `json:"identityCardFrontUrl,omitempty"`
	IdentityCardBackURL  string               `json:"identityCardBackUrl,omitempty"`
	Note                 string               `json:"note,omitempty"`
	Status               claimmodel.Status    `json:"status"`
	ReviewerAccountID    string               `json:"reviewerAccountId,omitempty"`
	ReviewNote           string               `json:"reviewNote,omitempty"`
	CreatedAt            time.Time            `json:"createdAt"`
	UpdatedAt            time.Time            `json:"updatedAt"`
	ReviewedAt           *time.Time           `json:"reviewedAt,omitempty"`
}

type QueueQuery struct {
	HomepageID string
	Status     claimmodel.Status
	Cursor     string
	Limit      int
}

type ClaimRequestSlice struct {
	Items      []ClaimRequestView `json:"items"`
	NextCursor string             `json:"nextCursor,omitempty"`
}

func (f *Facade) ListQueue(
	ctx context.Context,
	query QueueQuery,
) (ClaimRequestSlice, error) {
	page, err := f.data.Queue.ListQueue(ctx, claimports.QueueQuery{
		HomepageID: strings.TrimSpace(query.HomepageID),
		Status:     query.Status,
		Cursor:     strings.TrimSpace(query.Cursor),
		Limit:      query.Limit,
	})
	if err != nil {
		return ClaimRequestSlice{}, unavailable(err)
	}
	result := ClaimRequestSlice{
		Items:      make([]ClaimRequestView, 0, len(page.Items)),
		NextCursor: page.NextCursor,
	}
	for _, snapshot := range page.Items {
		aggregate, restoreErr := claimmodel.Restore(snapshot)
		if restoreErr != nil {
			return ClaimRequestSlice{}, unavailable(restoreErr)
		}
		result.Items = append(result.Items, viewFromAggregate(aggregate))
	}
	return result, nil
}

func (f *Facade) Create(ctx context.Context, command CreateCommand) (ClaimRequestView, error) {
	command = normalizeCreate(command)
	actorID, err := requiredPersona(command.ActorPersonaID)
	if err != nil {
		return ClaimRequestView{}, err
	}
	command.ActorPersonaID = actorID
	if command.HomepageID == "" {
		return ClaimRequestView{}, generated.AppErrorFromInvalidArgument("homepageId is required")
	}
	digest, err := commandDigest("CreateHomepageClaimRequest", command)
	if err != nil {
		return ClaimRequestView{}, err
	}
	if replayed, found, replayErr := f.replay(
		ctx, actorID, "CreateHomepageClaimRequest", digest,
	); replayErr != nil || found {
		return replayed, replayErr
	}
	state, found, gateErr := f.data.Homepages.FindHomepageState(ctx, command.HomepageID)
	if gateErr != nil {
		return ClaimRequestView{}, unavailable(gateErr)
	}
	if !found || strings.TrimSpace(state.Status) != "published" {
		if strings.TrimSpace(state.Status) == "offline" {
			return ClaimRequestView{}, generated.AppErrorFromHomepageOffline(
				fmt.Sprintf("homepage %s is offline", command.HomepageID),
			)
		}
		return ClaimRequestView{}, generated.AppErrorFromHomepageNotFound(
			fmt.Sprintf("published homepage %s was not found", command.HomepageID),
		)
	}
	if strings.TrimSpace(state.ClaimStatus) == "claimed" {
		return ClaimRequestView{}, claimgenerated.AppErrorFromAlreadyClaimed(
			fmt.Sprintf("homepage %s is already claimed", command.HomepageID),
		)
	}
	if _, pending, findErr := f.data.Aggregates.FindPending(
		ctx, command.HomepageID, actorID,
	); findErr != nil {
		return ClaimRequestView{}, unavailable(findErr)
	} else if pending {
		return ClaimRequestView{}, claimgenerated.AppErrorFromDuplicatePendingClaim(
			"a pending claim request already exists for this persona and homepage",
		)
	}
	now := f.now().UTC()
	aggregate, err := claimmodel.Create(claimmodel.CreateParams{
		ID:                   f.newID(),
		HomepageID:           command.HomepageID,
		RequesterPersonaID:   actorID,
		ClaimTier:            command.ClaimTier,
		BusinessLicenseURL:   command.BusinessLicenseURL,
		ContactPhone:         command.ContactPhone,
		IdentityCardFrontURL: command.IdentityCardFrontURL,
		IdentityCardBackURL:  command.IdentityCardBackURL,
		Note:                 command.Note,
		Now:                  now,
	})
	if err != nil {
		return ClaimRequestView{}, mapDomainError(err)
	}
	return f.commit(ctx, actorID, aggregate, 0, "CreateHomepageClaimRequest", digest, EventClaimRequested, now)
}

func (f *Facade) Review(ctx context.Context, command ReviewCommand) (ClaimRequestView, error) {
	command = normalizeReview(command)
	actorID, err := requiredAccount(command.ActorAccountID)
	if err != nil {
		return ClaimRequestView{}, err
	}
	command.ActorAccountID = actorID
	if command.ClaimRequestID == "" || command.HomepageID == "" {
		return ClaimRequestView{}, generated.AppErrorFromInvalidArgument(
			"homepageId and claimRequestId are required",
		)
	}
	if command.TargetStatus != claimmodel.StatusApproved &&
		command.TargetStatus != claimmodel.StatusRejected {
		return ClaimRequestView{}, generated.AppErrorFromInvalidArgument(
			"claim review target must be approved or rejected",
		)
	}
	digest, err := commandDigest("ReviewHomepageClaimRequest", command)
	if err != nil {
		return ClaimRequestView{}, err
	}
	if replayed, found, replayErr := f.replay(
		ctx, actorID, "ReviewHomepageClaimRequest", digest,
	); replayErr != nil || found {
		return replayed, replayErr
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := f.data.Aggregates.Load(ctx, command.ClaimRequestID)
		if loadErr != nil {
			return ClaimRequestView{}, unavailable(loadErr)
		}
		if !found || aggregate.Snapshot().HomepageID != command.HomepageID {
			return ClaimRequestView{}, claimgenerated.AppErrorFromClaimNotFound(
				fmt.Sprintf("claim request %s was not found", command.ClaimRequestID),
			)
		}
		snapshot := aggregate.Snapshot()
		if actorID == snapshot.RequesterPersonaID {
			return ClaimRequestView{}, generated.AppErrorFromPermissionDenied(
				"claim requester cannot review own request",
			)
		}
		if aggregate.Status() != claimmodel.StatusPendingReview {
			if aggregate.Status() == command.TargetStatus {
				return f.recordNoop(
					ctx, actorID, aggregate, "ReviewHomepageClaimRequest", digest,
				)
			}
			return ClaimRequestView{}, generated.AppErrorFromVersionConflict(
				"claim request has already been reviewed to a different terminal status",
			)
		}
		expectedVersion := aggregate.Version()
		now := f.now().UTC()
		if reviewErr := aggregate.Review(claimmodel.ReviewParams{
			ReviewerAccountID: actorID,
			TargetStatus:      command.TargetStatus,
			ReviewNote:        command.ReviewNote,
			Now:               now,
		}); reviewErr != nil {
			return ClaimRequestView{}, mapDomainError(reviewErr)
		}
		result, commitErr := f.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"ReviewHomepageClaimRequest",
			digest,
			EventClaimReviewed,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return ClaimRequestView{}, commitErr
		}
	}
	panic("unreachable homepage claim review retry")
}

// Load 为后续 handler/Ops query 暴露对象级窄读取。
func (f *Facade) Load(ctx context.Context, claimRequestID string) (ClaimRequestView, error) {
	aggregate, found, err := f.data.Aggregates.Load(ctx, strings.TrimSpace(claimRequestID))
	if err != nil {
		return ClaimRequestView{}, unavailable(err)
	}
	if !found {
		return ClaimRequestView{}, claimgenerated.AppErrorFromClaimNotFound(
			fmt.Sprintf("claim request %s was not found", claimRequestID),
		)
	}
	return viewFromAggregate(aggregate), nil
}

type claimRequestedPayload struct {
	ClaimRequestID     string               `json:"claimRequestId"`
	HomepageID         string               `json:"homepageId"`
	RequesterPersonaID string               `json:"requesterPersonaId"`
	ClaimTier          claimmodel.ClaimTier `json:"claimTier"`
	Status             claimmodel.Status    `json:"status"`
	CreatedAt          time.Time            `json:"createdAt"`
	Version            int64                `json:"version"`
}

type claimReviewedPayload struct {
	ClaimRequestID     string            `json:"claimRequestId"`
	HomepageID         string            `json:"homepageId"`
	RequesterPersonaID string            `json:"requesterPersonaId"`
	Status             claimmodel.Status `json:"status"`
	ReviewerAccountID  string            `json:"reviewerAccountId"`
	ReviewedAt         time.Time         `json:"reviewedAt"`
	Version            int64             `json:"version"`
}

func (f *Facade) commit(
	ctx context.Context,
	actorID string,
	aggregate *claimmodel.HomepageClaimRequest,
	expectedVersion int64,
	commandName string,
	digest string,
	eventType string,
	now time.Time,
) (ClaimRequestView, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ClaimRequestView{}, err
	}
	payload, err := claimEventPayload(eventType, aggregate.Snapshot())
	if err != nil {
		return ClaimRequestView{}, err
	}
	result, err := f.data.Aggregates.Commit(ctx, claimports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.Add(receiptTTL),
		Events: []claimports.OutboxEvent{{
			EventID:          eventIdentifier(idempotencyKey, eventType),
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       now,
		}},
	})
	if err != nil {
		return ClaimRequestView{}, wrapStoreError(err)
	}
	if result.Aggregate == nil {
		return ClaimRequestView{}, unavailable(errors.New("claim request commit returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), nil
}

func claimEventPayload(eventType string, snapshot claimmodel.Snapshot) ([]byte, error) {
	var payload any
	switch eventType {
	case EventClaimRequested:
		payload = claimRequestedPayload{
			ClaimRequestID:     snapshot.ID,
			HomepageID:         snapshot.HomepageID,
			RequesterPersonaID: snapshot.RequesterPersonaID,
			ClaimTier:          snapshot.ClaimTier,
			Status:             snapshot.Status,
			CreatedAt:          snapshot.CreatedAt,
			Version:            snapshot.Version,
		}
	case EventClaimReviewed:
		if snapshot.ReviewedAt == nil {
			return nil, unavailable(errors.New("reviewed claim event requires reviewedAt"))
		}
		payload = claimReviewedPayload{
			ClaimRequestID:     snapshot.ID,
			HomepageID:         snapshot.HomepageID,
			RequesterPersonaID: snapshot.RequesterPersonaID,
			Status:             snapshot.Status,
			ReviewerAccountID:  snapshot.ReviewerAccountID,
			ReviewedAt:         snapshot.ReviewedAt.UTC(),
			Version:            snapshot.Version,
		}
	default:
		return nil, unavailable(fmt.Errorf("unsupported claim event type %q", eventType))
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, unavailable(err)
	}
	return encoded, nil
}

func (f *Facade) replay(
	ctx context.Context,
	actorID string,
	commandName string,
	digest string,
) (ClaimRequestView, bool, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ClaimRequestView{}, false, err
	}
	result, found, err := f.data.Receipts.FindReceipt(ctx, key, commandName, digest)
	if err != nil {
		return ClaimRequestView{}, false, wrapStoreError(err)
	}
	if !found {
		return ClaimRequestView{}, false, nil
	}
	if result.Aggregate == nil {
		return ClaimRequestView{}, false, unavailable(errors.New("claim receipt returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), true, nil
}

func (f *Facade) recordNoop(
	ctx context.Context,
	actorID string,
	aggregate *claimmodel.HomepageClaimRequest,
	commandName string,
	digest string,
) (ClaimRequestView, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return ClaimRequestView{}, err
	}
	result, err := f.data.Receipts.RecordNoopReceipt(ctx, claimports.NoopReceipt{
		Aggregate:        aggregate,
		IdempotencyKey:   key,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: f.now().UTC().Add(receiptTTL),
	})
	if err != nil {
		return ClaimRequestView{}, wrapStoreError(err)
	}
	if result.Aggregate == nil {
		return ClaimRequestView{}, unavailable(errors.New("claim no-op receipt returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), nil
}

func viewFromAggregate(aggregate *claimmodel.HomepageClaimRequest) ClaimRequestView {
	snapshot := aggregate.Snapshot()
	return ClaimRequestView{
		ClaimRequestID:       snapshot.ID,
		Version:              snapshot.Version,
		HomepageID:           snapshot.HomepageID,
		RequesterPersonaID:   snapshot.RequesterPersonaID,
		ClaimTier:            snapshot.ClaimTier,
		BusinessLicenseURL:   snapshot.BusinessLicenseURL,
		ContactPhone:         snapshot.ContactPhone,
		IdentityCardFrontURL: snapshot.IdentityCardFrontURL,
		IdentityCardBackURL:  snapshot.IdentityCardBackURL,
		Note:                 snapshot.Note,
		Status:               snapshot.Status,
		ReviewerAccountID:    snapshot.ReviewerAccountID,
		ReviewNote:           snapshot.ReviewNote,
		CreatedAt:            snapshot.CreatedAt,
		UpdatedAt:            snapshot.UpdatedAt,
		ReviewedAt:           snapshot.ReviewedAt,
	}
}

func normalizeCreate(command CreateCommand) CreateCommand {
	command.HomepageID = strings.TrimSpace(command.HomepageID)
	command.ActorPersonaID = strings.TrimSpace(command.ActorPersonaID)
	command.ClaimTier = claimmodel.ClaimTier(strings.TrimSpace(string(command.ClaimTier)))
	command.BusinessLicenseURL = strings.TrimSpace(command.BusinessLicenseURL)
	command.ContactPhone = strings.TrimSpace(command.ContactPhone)
	command.IdentityCardFrontURL = strings.TrimSpace(command.IdentityCardFrontURL)
	command.IdentityCardBackURL = strings.TrimSpace(command.IdentityCardBackURL)
	command.Note = strings.TrimSpace(command.Note)
	return command
}

func normalizeReview(command ReviewCommand) ReviewCommand {
	command.HomepageID = strings.TrimSpace(command.HomepageID)
	command.ClaimRequestID = strings.TrimSpace(command.ClaimRequestID)
	command.ActorAccountID = strings.TrimSpace(command.ActorAccountID)
	command.TargetStatus = claimmodel.Status(strings.TrimSpace(string(command.TargetStatus)))
	command.ReviewNote = strings.TrimSpace(command.ReviewNote)
	return command
}

func requiredPersona(actorID string) (string, error) {
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return "", generated.AppErrorFromPermissionDenied(
			"claim create requires a trusted persona actor",
		)
	}
	return actorID, nil
}

func requiredAccount(actorID string) (string, error) {
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return "", generated.AppErrorFromPermissionDenied(
			"claim review requires a trusted account actor",
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
			"homepage claim command requires Idempotency-Key",
		)
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "homepage-claim-request:" + hex.EncodeToString(sum[:]), nil
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
	return "hcr-event-" + hex.EncodeToString(sum[:16])
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, claimmodel.ErrInvalidMaterialURL):
		return claimgenerated.AppErrorFromInvalidClaimMaterialURL(err.Error())
	case errors.Is(err, claimmodel.ErrClaimMaterial):
		return claimgenerated.AppErrorFromClaimMaterialMissing(err.Error())
	case errors.Is(err, claimmodel.ErrReviewerRequired),
		errors.Is(err, claimmodel.ErrSelfReview):
		return generated.AppErrorFromPermissionDenied(err.Error())
	case errors.Is(err, claimmodel.ErrAlreadyReviewed):
		return generated.AppErrorFromVersionConflict(err.Error())
	case errors.Is(err, claimmodel.ErrInvalidClaimRequest),
		errors.Is(err, claimmodel.ErrInvalidClaimTier),
		errors.Is(err, claimmodel.ErrInvalidReviewStatus):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return unavailable(err)
	}
}

func isVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == generated.ErrVersionConflict.Error()
}

func wrapStoreError(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return unavailable(err)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return generated.AppErrorFromInternalError(err.Error())
}
