package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
)

type Service struct {
	store       ports.Store
	memberships ports.MembershipAuthority
	trips       ports.TripAuthority
	assignments ports.AssignmentAuthority
	references  ports.ReferenceAuthority
	ids         ports.IDGenerator
	now         func() time.Time
}

func NewService(
	store ports.Store,
	memberships ports.MembershipAuthority,
	trips ports.TripAuthority,
	assignments ports.AssignmentAuthority,
	references ports.ReferenceAuthority,
	ids ports.IDGenerator,
	now func() time.Time,
) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{
		store: store, memberships: memberships, trips: trips, assignments: assignments,
		references: references, ids: ids, now: now,
	}
}

type CreateCommand struct {
	ActorPersonaID   string
	IdempotencyKey   string
	TripID           string
	RevisionNumber   int64
	DayIndex         *int
	ItemID           string
	Kind             model.Kind
	ContentRef       *model.ObjectRef
	InlineText       string
	CapturedAt       time.Time
	CoarsePlaceRef   *model.ObjectRef
	Visibility       model.Visibility
	AssignmentStatus model.AssignmentStatus
	SourceVersion    int64
}

type AssignCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	MomentID        string
	ExpectedVersion int64
	RevisionNumber  int64
	DayIndex        int
	ItemID          string
	Visibility      model.Visibility
	SourceVersion   int64
}

type DeleteCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	MomentID        string
	ExpectedVersion int64
	Reason          string
}

func (service *Service) Create(ctx context.Context, command CreateCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.memberships.CanViewTrip(ctx, command.ActorPersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.references.ValidateMomentReferences(
		ctx, command.Kind, command.ContentRef, command.CoarsePlaceRef, command.ActorPersonaID,
	); err != nil {
		return ports.CommandResult{}, err
	}
	if command.DayIndex != nil {
		if err := service.assignments.ValidateAssignment(
			ctx, command.TripID, command.RevisionNumber, *command.DayIndex, command.ItemID,
		); err != nil {
			return ports.CommandResult{}, err
		}
	}
	momentID, err := service.ids.NewTripMomentID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	moment, err := model.Create(model.CreateInput{
		MomentID: momentID, TripID: command.TripID, RevisionNumber: command.RevisionNumber,
		DayIndex: command.DayIndex, ItemID: command.ItemID, Kind: command.Kind,
		ContentRef: command.ContentRef, InlineText: command.InlineText, CapturedAt: command.CapturedAt,
		CoarsePlaceRef: command.CoarsePlaceRef, Visibility: command.Visibility,
		AssignmentStatus: command.AssignmentStatus, AttributionPersonaID: command.ActorPersonaID,
		SourceVersion: command.SourceVersion, Now: now,
	})
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, 0, moment, now)
}

func (service *Service) Assign(ctx context.Context, command AssignCommand) (ports.CommandResult, error) {
	if err := service.ready(
		command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.MomentID,
	); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.memberships.CanViewTrip(ctx, command.ActorPersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	moment, _, err := service.authorizedMoment(ctx, command.ActorPersonaID, command.TripID, command.MomentID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if err := service.assignments.ValidateAssignment(
		ctx, command.TripID, command.RevisionNumber, command.DayIndex, command.ItemID,
	); err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	next, err := moment.Assign(
		command.ExpectedVersion, command.RevisionNumber, command.DayIndex,
		command.ItemID, command.Visibility, command.SourceVersion, now,
	)
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, moment.Version, next, now)
}

func (service *Service) Delete(ctx context.Context, command DeleteCommand) (ports.CommandResult, error) {
	if err := service.ready(
		command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.MomentID,
	); err != nil || strings.TrimSpace(command.Reason) == "" {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.memberships.CanViewTrip(ctx, command.ActorPersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	moment, organizerID, err := service.authorizedMoment(ctx, command.ActorPersonaID, command.TripID, command.MomentID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	next, err := moment.Delete(command.ExpectedVersion, command.ActorPersonaID, organizerID, now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, moment.Version, next, now)
}

func (service *Service) List(ctx context.Context, actorPersonaID, tripID string) ([]model.Moment, error) {
	if service == nil || service.store == nil || service.memberships == nil {
		return nil, model.ErrInvalidArgument
	}
	if err := service.memberships.CanViewTrip(
		ctx, strings.TrimSpace(actorPersonaID), strings.TrimSpace(tripID),
	); err != nil {
		return nil, err
	}
	return service.store.ListActive(ctx, strings.TrimSpace(tripID))
}

func (service *Service) authorizedMoment(
	ctx context.Context,
	actorPersonaID string,
	tripID string,
	momentID string,
) (model.Moment, string, error) {
	moment, err := service.store.Get(ctx, strings.TrimSpace(tripID), strings.TrimSpace(momentID))
	if err != nil {
		return model.Moment{}, "", err
	}
	organizerID, err := service.trips.OrganizerPersonaID(ctx, strings.TrimSpace(tripID))
	if err != nil {
		return model.Moment{}, "", err
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	organizerID = strings.TrimSpace(organizerID)
	if actorPersonaID != moment.AttributionPersonaID && actorPersonaID != organizerID {
		return model.Moment{}, "", model.ErrPermissionDenied
	}
	return moment, organizerID, nil
}

func (service *Service) ready(values ...string) error {
	if service == nil || service.store == nil || service.memberships == nil || service.trips == nil ||
		service.assignments == nil || service.references == nil || service.ids == nil {
		return model.ErrInvalidArgument
	}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return model.ErrInvalidArgument
		}
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

func (service *Service) persist(
	ctx context.Context,
	key string,
	digest string,
	expectedVersion int64,
	moment model.Moment,
	now time.Time,
) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Moment: moment}
	commit := ports.Commit{
		ExpectedVersion: expectedVersion,
		Moment:          moment,
		Receipt: ports.Receipt{
			IdempotencyKey: key, CommandDigest: digest, Result: result,
			ExpiresAt: now.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID: eventID, EventType: "TripMomentChanged", AggregateID: moment.MomentID,
			AggregateVersion: moment.Version, OccurredAt: now,
			Payload: map[string]any{
				"momentId": moment.MomentID, "tripId": moment.TripID, "version": moment.Version,
				"revisionNumber": moment.RevisionNumber, "dayIndex": moment.DayIndex,
				"itemId": moment.ItemID, "assignmentStatus": moment.AssignmentStatus,
				"status": moment.Status, "sourceVersion": moment.SourceVersion,
			},
		},
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		if errors.Is(err, ports.ErrCommitConflict) {
			if replay, handled, replayErr := service.replay(ctx, key, digest); handled || replayErr != nil {
				return replay, replayErr
			}
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		return ports.CommandResult{}, err
	}
	return result, nil
}

func commandDigest(command any) string {
	raw, _ := json.Marshal(command)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}
