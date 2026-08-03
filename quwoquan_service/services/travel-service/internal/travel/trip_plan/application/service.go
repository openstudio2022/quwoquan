package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	revisionports "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

type IDGenerator interface {
	NewTripPlanID() (string, error)
	NewRevisionID() (string, error)
	NewEventID() (string, error)
}

var (
	ErrTemplateNotFound         = errors.New("trip plan template not found")
	ErrTemplatePermissionDenied = errors.New("trip plan template permission denied")
	ErrTemplateUnavailable      = errors.New("trip plan template unavailable")
)

type TemplateSnapshot struct {
	TemplateID     string
	Version        int64
	OwnerPersonaID string
	Title          string
	Items          []TemplateItem
	Attributions   []model.SourceAttribution
}

type TemplateItem struct {
	TemplateItemID string
	DayOffset      int
	OrderInDay     int
	Kind           model.ItemKind
	Title          string
	PublicPlaceRef *model.PlaceRef
	Note           string
}

type TemplateSource interface {
	GetOwnedActive(context.Context, string, string) (TemplateSnapshot, error)
}

type Service struct {
	store     ports.Store
	revisions revisionports.Reader
	templates TemplateSource
	ids       IDGenerator
	now       func() time.Time
}

func NewService(store ports.Store, revisions revisionports.Reader, templates TemplateSource, ids IDGenerator, now func() time.Time) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, revisions: revisions, templates: templates, ids: ids, now: now}
}

type ItemInput struct {
	ItemID     string
	DayIndex   int
	OrderInDay int
	Kind       model.ItemKind
	Title      string
	StartAt    *time.Time
	EndAt      *time.Time
	PlaceRef   *model.PlaceRef
	Note       string
}

type CreateCommand struct {
	ActorPersonaID string
	IdempotencyKey string
	Title          string
	StartAt        *time.Time
	EndAt          *time.Time
	Items          []ItemInput
}

type CreateFromTemplateCommand struct {
	ActorPersonaID string
	IdempotencyKey string
	TemplateID     string
	Title          string
	StartAt        *time.Time
	EndAt          *time.Time
}

type ReviseCommand struct {
	ActorPersonaID         string
	IdempotencyKey         string
	TripID                 string
	ExpectedRevisionNumber int64
	ChangeReason           string
	Severity               revisionmodel.Severity
	Items                  []ItemInput
	AffectedPersonaIDs     []string
}

type TransitionCommand struct {
	ActorPersonaID         string
	IdempotencyKey         string
	TripID                 string
	ExpectedRevisionNumber int64
	TargetStatus           model.Status
}

type ListQuery struct {
	ActorPersonaID string
	Status         model.Status
	Cursor         string
	Limit          int
}

func (service *Service) Create(ctx context.Context, command CreateCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	return service.createResolved(
		ctx, command.IdempotencyKey, digest, command.ActorPersonaID, command.Title,
		command.StartAt, command.EndAt, command.Items, "", 0, nil,
	)
}

func (service *Service) CreateFromTemplate(ctx context.Context, command CreateFromTemplateCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey); err != nil ||
		service.templates == nil || strings.TrimSpace(command.TemplateID) == "" {
		return ports.CommandResult{}, model.ErrInvalidInput
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	template, err := service.templates.GetOwnedActive(
		ctx, strings.TrimSpace(command.ActorPersonaID), strings.TrimSpace(command.TemplateID),
	)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if strings.TrimSpace(template.TemplateID) != strings.TrimSpace(command.TemplateID) ||
		strings.TrimSpace(template.OwnerPersonaID) != strings.TrimSpace(command.ActorPersonaID) ||
		template.Version <= 0 || template.Items == nil || template.Attributions == nil {
		return ports.CommandResult{}, ErrTemplateUnavailable
	}
	title := strings.TrimSpace(command.Title)
	if title == "" {
		title = strings.TrimSpace(template.Title)
	}
	items := make([]ItemInput, 0, len(template.Items))
	for _, item := range template.Items {
		items = append(items, ItemInput{
			ItemID: item.TemplateItemID, DayIndex: item.DayOffset, OrderInDay: item.OrderInDay,
			Kind: item.Kind, Title: templateItemTitle(item.Kind, item.Title),
			PlaceRef: clonePlaceRef(item.PublicPlaceRef), Note: item.Note,
		})
	}
	return service.createResolved(
		ctx, command.IdempotencyKey, digest, command.ActorPersonaID, title,
		command.StartAt, command.EndAt, items, template.TemplateID, template.Version,
		template.Attributions,
	)
}

func (service *Service) createResolved(
	ctx context.Context,
	idempotencyKey, digest, actorPersonaID, title string,
	startAt, endAt *time.Time,
	items []ItemInput,
	sourceTemplateID string,
	sourceTemplateVersion int64,
	sourceAttributions []model.SourceAttribution,
) (ports.CommandResult, error) {
	tripID, err := service.ids.NewTripPlanID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	revisionID, err := service.ids.NewRevisionID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	plan, revision, err := model.Create(model.CreateInput{
		TripID:                tripID,
		RevisionID:            revisionID,
		OrganizerPersonaID:    strings.TrimSpace(actorPersonaID),
		Title:                 title,
		StartAt:               startAt,
		EndAt:                 endAt,
		Items:                 toItems(items),
		SourceTemplateID:      strings.TrimSpace(sourceTemplateID),
		SourceTemplateVersion: sourceTemplateVersion,
		SourceAttributions:    sourceAttributions,
		Now:                   now,
	})
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := resultFrom(plan, false)
	commit, err := service.commit(idempotencyKey, digest, 0, 0, plan, revision, result, "TripPlanCreated", now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		return service.resolveCommitError(ctx, idempotencyKey, digest, err)
	}
	return result, nil
}

func templateItemTitle(kind model.ItemKind, title string) string {
	if value := strings.TrimSpace(title); value != "" {
		return value
	}
	switch kind {
	case model.ItemStay:
		return "住宿待确认"
	case model.ItemFood:
		return "餐饮待确认"
	case model.ItemSight:
		return "景点待确认"
	case model.ItemActivity:
		return "活动待确认"
	case model.ItemTransport:
		return "交通待确认"
	case model.ItemRest:
		return "休息"
	case model.ItemFreeTime:
		return "自由活动"
	default:
		return "行程事项"
	}
}

func clonePlaceRef(value *model.PlaceRef) *model.PlaceRef {
	if value == nil {
		return nil
	}
	return &model.PlaceRef{ObjectTypeRef: value.ObjectTypeRef, ObjectID: value.ObjectID}
}

func (service *Service) Revise(ctx context.Context, command ReviseCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	plan, err := service.store.GetPlan(ctx, strings.TrimSpace(command.TripID))
	if err != nil {
		return ports.CommandResult{}, err
	}
	previous, err := service.getRevision(ctx, plan.TripID, plan.CurrentRevisionNumber)
	if err != nil {
		return ports.CommandResult{}, err
	}
	revisionID, err := service.ids.NewRevisionID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	nextPlan, revision, err := plan.Revise(
		command.ActorPersonaID,
		command.ExpectedRevisionNumber,
		revisionID,
		command.ChangeReason,
		command.Severity,
		previous.Items,
		toItems(command.Items),
		command.AffectedPersonaIDs,
		now,
	)
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := resultFrom(nextPlan, false)
	commit, err := service.commit(command.IdempotencyKey, digest, plan.Version, plan.CurrentRevisionNumber, nextPlan, revision, result, "TripPlanRevised", now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		return service.resolveCommitError(ctx, command.IdempotencyKey, digest, err)
	}
	return result, nil
}

func (service *Service) Transition(ctx context.Context, command TransitionCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	plan, err := service.store.GetPlan(ctx, strings.TrimSpace(command.TripID))
	if err != nil {
		return ports.CommandResult{}, err
	}
	previous, err := service.getRevision(ctx, plan.TripID, plan.CurrentRevisionNumber)
	if err != nil {
		return ports.CommandResult{}, err
	}
	revisionID, err := service.ids.NewRevisionID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	nextPlan, revision, err := plan.Transition(
		command.ActorPersonaID,
		command.ExpectedRevisionNumber,
		revisionID,
		command.TargetStatus,
		previous.Items,
		now,
	)
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := resultFrom(nextPlan, false)
	commit, err := service.commit(command.IdempotencyKey, digest, plan.Version, plan.CurrentRevisionNumber, nextPlan, revision, result, "TripPlanLifecycleChanged", now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		return service.resolveCommitError(ctx, command.IdempotencyKey, digest, err)
	}
	return result, nil
}

func (service *Service) Get(ctx context.Context, actorPersonaID, tripID string) (model.Plan, revisionmodel.Revision, error) {
	plan, err := service.store.GetPlan(ctx, strings.TrimSpace(tripID))
	if err != nil {
		return model.Plan{}, revisionmodel.Revision{}, err
	}
	if strings.TrimSpace(actorPersonaID) != plan.OrganizerPersonaID {
		return model.Plan{}, revisionmodel.Revision{}, model.ErrPermissionDenied
	}
	revision, err := service.getRevision(ctx, plan.TripID, plan.CurrentRevisionNumber)
	return plan, revision, err
}

func (service *Service) List(ctx context.Context, query ListQuery) (ports.PlanPage, error) {
	actorPersonaID := strings.TrimSpace(query.ActorPersonaID)
	if service == nil || service.store == nil || actorPersonaID == "" || !validListStatus(query.Status) {
		return ports.PlanPage{}, model.ErrInvalidInput
	}
	limit := query.Limit
	if limit == 0 {
		limit = 20
	}
	if limit < 1 || limit > 50 {
		return ports.PlanPage{}, model.ErrInvalidInput
	}
	return service.store.ListPlans(ctx, ports.ListQuery{
		OrganizerPersonaID: actorPersonaID,
		Status:             query.Status,
		Cursor:             strings.TrimSpace(query.Cursor),
		Limit:              limit,
	})
}

func validListStatus(status model.Status) bool {
	switch status {
	case "", model.StatusPlanning, model.StatusActive, model.StatusCompleted, model.StatusArchived:
		return true
	default:
		return false
	}
}

// OrganizerPersonaID exposes the minimal TripPlan authority needed by sibling
// Travel aggregates without leaking TripPlan persistence or mutable state.
func (service *Service) OrganizerPersonaID(ctx context.Context, tripID string) (string, error) {
	if service == nil || service.store == nil {
		return "", model.ErrInvalidInput
	}
	plan, err := service.store.GetPlan(ctx, strings.TrimSpace(tripID))
	if err != nil {
		return "", err
	}
	return plan.OrganizerPersonaID, nil
}

func (service *Service) ready(actorPersonaID, idempotencyKey string) error {
	if service == nil || service.store == nil || service.revisions == nil || service.ids == nil ||
		strings.TrimSpace(actorPersonaID) == "" || strings.TrimSpace(idempotencyKey) == "" {
		return model.ErrInvalidInput
	}
	return nil
}

func (service *Service) replay(ctx context.Context, key, digest string) (ports.CommandResult, bool, error) {
	receipt, found, err := service.store.FindReceipt(ctx, strings.TrimSpace(key))
	if err != nil || !found {
		return ports.CommandResult{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommandResult{}, true, ports.ErrIdempotencyConflict
	}
	result := receipt.Result
	result.IdempotentReplay = true
	return result, true, nil
}

func (service *Service) resolveCommitError(ctx context.Context, key, digest string, commitErr error) (ports.CommandResult, error) {
	if errors.Is(commitErr, ports.ErrCommitConflict) {
		if result, handled, replayErr := service.replay(ctx, key, digest); handled || replayErr != nil {
			return result, replayErr
		}
		return ports.CommandResult{}, model.ErrRevisionConflict
	}
	return ports.CommandResult{}, commitErr
}

func (service *Service) commit(
	key, digest string,
	expectedVersion, expectedRevision int64,
	plan model.Plan,
	revision revisionmodel.Revision,
	result ports.CommandResult,
	eventType string,
	now time.Time,
) (ports.Commit, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.Commit{}, err
	}
	revisionEventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.Commit{}, err
	}
	return ports.Commit{
		ExpectedPlanVersion:    expectedVersion,
		ExpectedRevisionNumber: expectedRevision,
		Plan:                   plan,
		Revision:               revision,
		Receipt: ports.CommandReceipt{
			IdempotencyKey: key,
			CommandDigest:  digest,
			Result:         result,
			ExpiresAt:      now.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      plan.TripID,
			AggregateVersion: plan.Version,
			Payload: map[string]any{
				"id":                    plan.TripID,
				"tripId":                plan.TripID,
				"organizerPersonaId":    plan.OrganizerPersonaID,
				"status":                plan.Status,
				"sourceTemplateId":      nullableSourceTemplateID(plan),
				"sourceTemplateVersion": nullableSourceTemplateVersion(plan),
				"currentRevisionId":     plan.CurrentRevisionID,
				"currentRevisionNumber": plan.CurrentRevisionNumber,
				"createdAt":             plan.CreatedAt,
				"updatedAt":             plan.UpdatedAt,
			},
			OccurredAt: now,
		},
		RevisionEvent: ports.OutboxEvent{
			EventID:          revisionEventID,
			EventType:        "TripPlanRevisionAppended",
			AggregateID:      revision.RevisionID,
			AggregateVersion: revision.RevisionNumber,
			Payload: map[string]any{
				"id":                 revision.RevisionID,
				"tripId":             revision.TripID,
				"revisionNumber":     revision.RevisionNumber,
				"previousRevisionId": revision.PreviousRevisionID,
				"changeReason":       revision.ChangeReason,
				"severity":           revision.Severity,
				"changes":            revision.Changes,
				"affectedPersonaIds": revision.AffectedPersonaIDs,
				"createdByPersonaId": revision.CreatedByPersonaID,
				"createdAt":          revision.CreatedAt,
			},
			OccurredAt: now,
		},
	}, nil
}

func nullableSourceTemplateID(plan model.Plan) any {
	if strings.TrimSpace(plan.SourceTemplateID) == "" {
		return nil
	}
	return plan.SourceTemplateID
}

func nullableSourceTemplateVersion(plan model.Plan) any {
	if plan.SourceTemplateVersion == 0 {
		return nil
	}
	return plan.SourceTemplateVersion
}

func (service *Service) getRevision(ctx context.Context, tripID string, number int64) (revisionmodel.Revision, error) {
	revision, err := service.revisions.Get(ctx, tripID, number)
	if errors.Is(err, revisionports.ErrNotFound) {
		return revisionmodel.Revision{}, ports.ErrNotFound
	}
	return revision, err
}

func toItems(inputs []ItemInput) []model.Item {
	items := make([]model.Item, 0, len(inputs))
	for _, input := range inputs {
		items = append(items, model.Item{
			ItemID: input.ItemID, DayIndex: input.DayIndex, OrderInDay: input.OrderInDay,
			Kind: input.Kind, Title: input.Title, StartAt: input.StartAt, EndAt: input.EndAt,
			PlaceRef: input.PlaceRef, Note: input.Note,
		})
	}
	return items
}

func resultFrom(plan model.Plan, replay bool) ports.CommandResult {
	return ports.CommandResult{
		TripID: plan.TripID, Version: plan.Version, CurrentRevisionID: plan.CurrentRevisionID,
		CurrentRevisionNumber: plan.CurrentRevisionNumber, Status: plan.Status, IdempotentReplay: replay,
	}
}

func commandDigest(command any) string {
	raw, _ := json.Marshal(command)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}
