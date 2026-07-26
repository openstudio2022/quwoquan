// Package homepage_status_report 实现 HomepageStatusReport 对象专属 Facade。
package homepage_status_report

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
	reportgenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage_status_report"
	reportmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/model"
	reportports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/ports"
)

const (
	receiptTTL = 24 * time.Hour

	EventStatusReported       = "HomepageStatusReported"
	EventStatusReportReviewed = "HomepageStatusReportReviewed"
)

type HomepageGate interface {
	FindHomepageStatus(ctx context.Context, homepageID string) (status string, found bool, err error)
}

type DataPorts struct {
	Aggregates reportports.AggregateStore
	Receipts   reportports.ReceiptStore
	Homepages  HomepageGate
	Queue      reportports.QueueReader
}

type Facade struct {
	data  DataPorts
	now   func() time.Time
	newID func() string
}

func NewFacade(data DataPorts) (*Facade, error) {
	if data.Aggregates == nil || data.Receipts == nil || data.Homepages == nil || data.Queue == nil {
		return nil, errors.New(
			"homepage status report facade requires aggregate, receipt, homepage and queue reader ports",
		)
	}
	return &Facade{
		data: data,
		now:  time.Now,
		newID: func() string {
			return "hsr_" + uuid.NewString()
		},
	}, nil
}

func (f *Facade) SetClock(now func() time.Time) {
	if now != nil {
		f.now = now
	}
}

func (f *Facade) SetIDGenerator(generator func() string) {
	if generator != nil {
		f.newID = generator
	}
}

type CreateCommand struct {
	HomepageID     string
	ActorPersonaID string
	Reason         reportmodel.Reason
	Description    string
	EvidenceURLs   []string
}

type ReviewCommand struct {
	HomepageID     string
	ReportID       string
	ActorAccountID string
	TargetStatus   reportmodel.Status
	ReviewNote     string
}

type StatusReportView struct {
	ReportID          string             `json:"reportId"`
	Version           int64              `json:"version"`
	HomepageID        string             `json:"homepageId"`
	ReporterPersonaID string             `json:"reporterPersonaId"`
	Reason            reportmodel.Reason `json:"reason"`
	Description       string             `json:"description,omitempty"`
	EvidenceURLs      []string           `json:"evidenceUrls,omitempty"`
	Status            reportmodel.Status `json:"status"`
	ReviewerAccountID string             `json:"reviewerAccountId,omitempty"`
	ReviewNote        string             `json:"reviewNote,omitempty"`
	CreatedAt         time.Time          `json:"createdAt"`
	UpdatedAt         time.Time          `json:"updatedAt"`
	ReviewedAt        *time.Time         `json:"reviewedAt,omitempty"`
}

type QueueQuery struct {
	HomepageID string
	Status     reportmodel.Status
	Cursor     string
	Limit      int
}

type StatusReportSlice struct {
	Items      []StatusReportView `json:"items"`
	NextCursor string             `json:"nextCursor,omitempty"`
}

func (f *Facade) ListQueue(
	ctx context.Context,
	query QueueQuery,
) (StatusReportSlice, error) {
	page, err := f.data.Queue.ListQueue(ctx, reportports.QueueQuery{
		HomepageID: strings.TrimSpace(query.HomepageID),
		Status:     query.Status,
		Cursor:     strings.TrimSpace(query.Cursor),
		Limit:      query.Limit,
	})
	if err != nil {
		return StatusReportSlice{}, unavailable(err)
	}
	result := StatusReportSlice{
		Items:      make([]StatusReportView, 0, len(page.Items)),
		NextCursor: page.NextCursor,
	}
	for _, snapshot := range page.Items {
		aggregate, restoreErr := reportmodel.Restore(snapshot)
		if restoreErr != nil {
			return StatusReportSlice{}, unavailable(restoreErr)
		}
		result.Items = append(result.Items, viewFromAggregate(aggregate))
	}
	return result, nil
}

func (f *Facade) Create(ctx context.Context, command CreateCommand) (StatusReportView, error) {
	command = normalizeCreate(command)
	actorID, err := requiredPersona(command.ActorPersonaID)
	if err != nil {
		return StatusReportView{}, err
	}
	command.ActorPersonaID = actorID
	if command.HomepageID == "" {
		return StatusReportView{}, generated.AppErrorFromInvalidArgument("homepageId is required")
	}
	digest, err := commandDigest("CreateHomepageStatusReport", command)
	if err != nil {
		return StatusReportView{}, err
	}
	if replayed, found, replayErr := f.replay(
		ctx, actorID, "CreateHomepageStatusReport", digest,
	); replayErr != nil || found {
		return replayed, replayErr
	}
	_, found, gateErr := f.data.Homepages.FindHomepageStatus(ctx, command.HomepageID)
	if gateErr != nil {
		return StatusReportView{}, unavailable(gateErr)
	}
	if !found {
		return StatusReportView{}, generated.AppErrorFromHomepageNotFound(
			fmt.Sprintf("homepage %s was not found", command.HomepageID),
		)
	}
	if _, pending, findErr := f.data.Aggregates.FindPending(
		ctx, command.HomepageID, actorID, command.Reason,
	); findErr != nil {
		return StatusReportView{}, unavailable(findErr)
	} else if pending {
		return StatusReportView{}, generated.AppErrorFromInvalidArgument(
			"a pending status report already exists for this persona, homepage and reason",
		)
	}
	now := f.now().UTC()
	aggregate, err := reportmodel.Create(reportmodel.CreateParams{
		ID:                f.newID(),
		HomepageID:        command.HomepageID,
		ReporterPersonaID: actorID,
		Reason:            command.Reason,
		Description:       command.Description,
		EvidenceURLs:      command.EvidenceURLs,
		Now:               now,
	})
	if err != nil {
		return StatusReportView{}, mapDomainError(err)
	}
	return f.commit(
		ctx,
		actorID,
		aggregate,
		0,
		"CreateHomepageStatusReport",
		digest,
		EventStatusReported,
		now,
	)
}

func (f *Facade) Review(ctx context.Context, command ReviewCommand) (StatusReportView, error) {
	command = normalizeReview(command)
	actorID, err := requiredAccount(command.ActorAccountID)
	if err != nil {
		return StatusReportView{}, err
	}
	command.ActorAccountID = actorID
	if command.ReportID == "" || command.HomepageID == "" {
		return StatusReportView{}, generated.AppErrorFromInvalidArgument(
			"homepageId and reportId are required",
		)
	}
	if command.TargetStatus != reportmodel.StatusConfirmedOffline &&
		command.TargetStatus != reportmodel.StatusDismissed {
		return StatusReportView{}, generated.AppErrorFromInvalidArgument(
			"status report review target must be confirmed_offline or dismissed",
		)
	}
	digest, err := commandDigest("ReviewHomepageStatusReport", command)
	if err != nil {
		return StatusReportView{}, err
	}
	if replayed, found, replayErr := f.replay(
		ctx, actorID, "ReviewHomepageStatusReport", digest,
	); replayErr != nil || found {
		return replayed, replayErr
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := f.data.Aggregates.Load(ctx, command.ReportID)
		if loadErr != nil {
			return StatusReportView{}, unavailable(loadErr)
		}
		if !found || aggregate.Snapshot().HomepageID != command.HomepageID {
			return StatusReportView{}, reportgenerated.AppErrorFromStatusReportNotFound(
				fmt.Sprintf("status report %s was not found", command.ReportID),
			)
		}
		snapshot := aggregate.Snapshot()
		if actorID == snapshot.ReporterPersonaID {
			return StatusReportView{}, generated.AppErrorFromPermissionDenied(
				"status reporter cannot review own report",
			)
		}
		if aggregate.Status() != reportmodel.StatusPendingReview {
			if aggregate.Status() == command.TargetStatus {
				return f.recordNoop(
					ctx, actorID, aggregate, "ReviewHomepageStatusReport", digest,
				)
			}
			return StatusReportView{}, generated.AppErrorFromVersionConflict(
				"status report has already been reviewed to a different terminal status",
			)
		}
		expectedVersion := aggregate.Version()
		now := f.now().UTC()
		if reviewErr := aggregate.Review(reportmodel.ReviewParams{
			ReviewerAccountID: actorID,
			TargetStatus:      command.TargetStatus,
			ReviewNote:        command.ReviewNote,
			Now:               now,
		}); reviewErr != nil {
			return StatusReportView{}, mapDomainError(reviewErr)
		}
		result, commitErr := f.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"ReviewHomepageStatusReport",
			digest,
			EventStatusReportReviewed,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isVersionConflict(commitErr) || attempt == 2 {
			return StatusReportView{}, commitErr
		}
	}
	panic("unreachable homepage status report review retry")
}

// Load 为后续 handler/Ops query 暴露对象级窄读取。
func (f *Facade) Load(ctx context.Context, reportID string) (StatusReportView, error) {
	aggregate, found, err := f.data.Aggregates.Load(ctx, strings.TrimSpace(reportID))
	if err != nil {
		return StatusReportView{}, unavailable(err)
	}
	if !found {
		return StatusReportView{}, reportgenerated.AppErrorFromStatusReportNotFound(
			fmt.Sprintf("status report %s was not found", reportID),
		)
	}
	return viewFromAggregate(aggregate), nil
}

type statusReportedPayload struct {
	ReportID          string             `json:"reportId"`
	HomepageID        string             `json:"homepageId"`
	ReporterPersonaID string             `json:"reporterPersonaId"`
	Reason            reportmodel.Reason `json:"reason"`
	Status            reportmodel.Status `json:"status"`
	CreatedAt         time.Time          `json:"createdAt"`
	Version           int64              `json:"version"`
}

type statusReportReviewedPayload struct {
	ReportID          string             `json:"reportId"`
	HomepageID        string             `json:"homepageId"`
	ReporterPersonaID string             `json:"reporterPersonaId"`
	Status            reportmodel.Status `json:"status"`
	ReviewerAccountID string             `json:"reviewerAccountId"`
	ReviewedAt        time.Time          `json:"reviewedAt"`
	Version           int64              `json:"version"`
}

func (f *Facade) commit(
	ctx context.Context,
	actorID string,
	aggregate *reportmodel.HomepageStatusReport,
	expectedVersion int64,
	commandName string,
	digest string,
	eventType string,
	now time.Time,
) (StatusReportView, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return StatusReportView{}, err
	}
	payload, err := eventPayload(eventType, aggregate.Snapshot())
	if err != nil {
		return StatusReportView{}, err
	}
	result, err := f.data.Aggregates.Commit(ctx, reportports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.Add(receiptTTL),
		Events: []reportports.OutboxEvent{{
			EventID:          eventIdentifier(idempotencyKey, eventType),
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       now,
		}},
	})
	if err != nil {
		return StatusReportView{}, wrapStoreError(err)
	}
	if result.Aggregate == nil {
		return StatusReportView{}, unavailable(errors.New("status report commit returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), nil
}

func eventPayload(eventType string, snapshot reportmodel.Snapshot) ([]byte, error) {
	var payload any
	switch eventType {
	case EventStatusReported:
		payload = statusReportedPayload{
			ReportID:          snapshot.ID,
			HomepageID:        snapshot.HomepageID,
			ReporterPersonaID: snapshot.ReporterPersonaID,
			Reason:            snapshot.Reason,
			Status:            snapshot.Status,
			CreatedAt:         snapshot.CreatedAt,
			Version:           snapshot.Version,
		}
	case EventStatusReportReviewed:
		if snapshot.ReviewedAt == nil {
			return nil, unavailable(errors.New("reviewed status report event requires reviewedAt"))
		}
		payload = statusReportReviewedPayload{
			ReportID:          snapshot.ID,
			HomepageID:        snapshot.HomepageID,
			ReporterPersonaID: snapshot.ReporterPersonaID,
			Status:            snapshot.Status,
			ReviewerAccountID: snapshot.ReviewerAccountID,
			ReviewedAt:        snapshot.ReviewedAt.UTC(),
			Version:           snapshot.Version,
		}
	default:
		return nil, unavailable(fmt.Errorf("unsupported status report event type %q", eventType))
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
) (StatusReportView, bool, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return StatusReportView{}, false, err
	}
	result, found, err := f.data.Receipts.FindReceipt(ctx, key, commandName, digest)
	if err != nil {
		return StatusReportView{}, false, wrapStoreError(err)
	}
	if !found {
		return StatusReportView{}, false, nil
	}
	if result.Aggregate == nil {
		return StatusReportView{}, false, unavailable(errors.New("status report receipt returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), true, nil
}

func (f *Facade) recordNoop(
	ctx context.Context,
	actorID string,
	aggregate *reportmodel.HomepageStatusReport,
	commandName string,
	digest string,
) (StatusReportView, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return StatusReportView{}, err
	}
	result, err := f.data.Receipts.RecordNoopReceipt(ctx, reportports.NoopReceipt{
		Aggregate:        aggregate,
		IdempotencyKey:   key,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: f.now().UTC().Add(receiptTTL),
	})
	if err != nil {
		return StatusReportView{}, wrapStoreError(err)
	}
	if result.Aggregate == nil {
		return StatusReportView{}, unavailable(errors.New("status report no-op receipt returned no aggregate"))
	}
	return viewFromAggregate(result.Aggregate), nil
}

func viewFromAggregate(aggregate *reportmodel.HomepageStatusReport) StatusReportView {
	snapshot := aggregate.Snapshot()
	return StatusReportView{
		ReportID:          snapshot.ID,
		Version:           snapshot.Version,
		HomepageID:        snapshot.HomepageID,
		ReporterPersonaID: snapshot.ReporterPersonaID,
		Reason:            snapshot.Reason,
		Description:       snapshot.Description,
		EvidenceURLs:      append([]string(nil), snapshot.EvidenceURLs...),
		Status:            snapshot.Status,
		ReviewerAccountID: snapshot.ReviewerAccountID,
		ReviewNote:        snapshot.ReviewNote,
		CreatedAt:         snapshot.CreatedAt,
		UpdatedAt:         snapshot.UpdatedAt,
		ReviewedAt:        snapshot.ReviewedAt,
	}
}

func normalizeCreate(command CreateCommand) CreateCommand {
	command.HomepageID = strings.TrimSpace(command.HomepageID)
	command.ActorPersonaID = strings.TrimSpace(command.ActorPersonaID)
	command.Reason = reportmodel.Reason(strings.TrimSpace(string(command.Reason)))
	command.Description = strings.TrimSpace(command.Description)
	command.EvidenceURLs = normalizeStrings(command.EvidenceURLs)
	return command
}

func normalizeReview(command ReviewCommand) ReviewCommand {
	command.HomepageID = strings.TrimSpace(command.HomepageID)
	command.ReportID = strings.TrimSpace(command.ReportID)
	command.ActorAccountID = strings.TrimSpace(command.ActorAccountID)
	command.TargetStatus = reportmodel.Status(strings.TrimSpace(string(command.TargetStatus)))
	command.ReviewNote = strings.TrimSpace(command.ReviewNote)
	return command
}

func normalizeStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	normalized := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, found := seen[value]; found {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	if len(normalized) == 0 {
		return nil
	}
	return normalized
}

func requiredPersona(actorID string) (string, error) {
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return "", generated.AppErrorFromPermissionDenied(
			"status report create requires a trusted persona actor",
		)
	}
	return actorID, nil
}

func requiredAccount(actorID string) (string, error) {
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return "", generated.AppErrorFromPermissionDenied(
			"status report review requires a trusted account actor",
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
			"homepage status report command requires Idempotency-Key",
		)
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "homepage-status-report:" + hex.EncodeToString(sum[:]), nil
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
	return "hsr-event-" + hex.EncodeToString(sum[:16])
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, reportmodel.ErrInvalidEvidenceURL):
		return reportgenerated.AppErrorFromInvalidStatusReportEvidenceURL(err.Error())
	case errors.Is(err, reportmodel.ErrReviewerRequired),
		errors.Is(err, reportmodel.ErrSelfReview):
		return generated.AppErrorFromPermissionDenied(err.Error())
	case errors.Is(err, reportmodel.ErrAlreadyReviewed):
		return generated.AppErrorFromVersionConflict(err.Error())
	case errors.Is(err, reportmodel.ErrInvalidStatusReport),
		errors.Is(err, reportmodel.ErrInvalidReason),
		errors.Is(err, reportmodel.ErrInvalidReviewStatus):
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
