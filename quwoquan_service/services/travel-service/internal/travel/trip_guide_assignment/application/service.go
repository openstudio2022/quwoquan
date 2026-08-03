package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

type Service struct {
	store       ports.Store
	trips       ports.TripAuthority
	memberships ports.MembershipAuthority
	personas    ports.PersonaAuthority
	ids         ports.IDGenerator
	now         func() time.Time
}

func NewService(store ports.Store, trips ports.TripAuthority, memberships ports.MembershipAuthority, personas ports.PersonaAuthority, ids ports.IDGenerator, now func() time.Time) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, trips: trips, memberships: memberships, personas: personas, ids: ids, now: now}
}

type PutCommand struct {
	ActorPersonaID, IdempotencyKey, TripID, TaskKey string
	ExpectedVersion                                 int64
	Input                                           model.PutInput
}
type TransitionCommand struct {
	ActorPersonaID, IdempotencyKey, TripID, TaskKey string
	ExpectedVersion                                 int64
	TargetStatus                                    model.Status
}

func (service *Service) Put(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.TaskKey); err != nil || command.ExpectedVersion < 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	organizer, err := service.trips.OrganizerPersonaID(ctx, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if strings.TrimSpace(organizer) != strings.TrimSpace(command.ActorPersonaID) {
		return ports.CommandResult{}, model.ErrPermissionDenied
	}
	if err := service.memberships.CanViewTrip(ctx, command.Input.AssigneePersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	if command.Input.Role == model.RoleLicensedGuide || strings.TrimSpace(command.Input.PublicQualificationPersonaID) != "" {
		if err := service.personas.ValidateGuidePersona(ctx, command.Input.AssigneePersonaID, command.Input.PublicQualificationPersonaID, command.Input.Role); err != nil {
			return ports.CommandResult{}, err
		}
	}
	current, getErr := service.store.Get(ctx, command.TripID, command.TaskKey)
	var assignment model.Assignment
	var expected int64
	switch {
	case errors.Is(getErr, ports.ErrNotFound):
		if command.ExpectedVersion != 0 {
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		assignmentID, idErr := service.ids.NewTripGuideAssignmentID()
		if idErr != nil {
			return ports.CommandResult{}, idErr
		}
		assignment, err = model.Create(assignmentID, command.TripID, command.TaskKey, command.ActorPersonaID, command.Input, service.now().UTC())
	case getErr != nil:
		return ports.CommandResult{}, getErr
	default:
		expected = current.Version
		assignment, err = current.Put(command.ExpectedVersion, command.Input, service.now().UTC())
	}
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, expected, assignment)
}

func (service *Service) Transition(ctx context.Context, command TransitionCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.TaskKey); err != nil || command.ExpectedVersion <= 0 || !command.TargetStatus.Valid() {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	assignment, err := service.store.Get(ctx, command.TripID, command.TaskKey)
	if err != nil {
		return ports.CommandResult{}, err
	}
	organizer, err := service.trips.OrganizerPersonaID(ctx, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	actor := strings.TrimSpace(command.ActorPersonaID)
	if actor != strings.TrimSpace(organizer) && actor != assignment.AssigneePersonaID {
		return ports.CommandResult{}, model.ErrPermissionDenied
	}
	if actor != assignment.AssigneePersonaID && command.TargetStatus != model.StatusCancelled {
		return ports.CommandResult{}, model.ErrPermissionDenied
	}
	next, err := assignment.Transition(command.ExpectedVersion, command.TargetStatus, service.now().UTC())
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, assignment.Version, next)
}

func (service *Service) List(ctx context.Context, actorPersonaID, tripID string) ([]model.Assignment, error) {
	if service == nil || service.store == nil || service.memberships == nil || strings.TrimSpace(actorPersonaID) == "" || strings.TrimSpace(tripID) == "" {
		return nil, model.ErrInvalidArgument
	}
	if err := service.memberships.CanViewTrip(ctx, strings.TrimSpace(actorPersonaID), strings.TrimSpace(tripID)); err != nil {
		return nil, err
	}
	return service.store.ListByTrip(ctx, strings.TrimSpace(tripID))
}

func (service *Service) ready(values ...string) error {
	if service == nil || service.store == nil || service.trips == nil || service.memberships == nil || service.personas == nil || service.ids == nil {
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

func (service *Service) persist(ctx context.Context, key, digest string, expectedVersion int64, assignment model.Assignment) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Assignment: assignment}
	commit := ports.Commit{ExpectedVersion: expectedVersion, Assignment: assignment,
		Receipt: ports.Receipt{IdempotencyKey: key, CommandDigest: digest, Result: result, ExpiresAt: assignment.UpdatedAt.Add(7 * 24 * time.Hour)},
		Event: ports.OutboxEvent{EventID: eventID, EventType: "TripGuideAssignmentChanged", AggregateID: assignment.AssignmentID, AggregateVersion: assignment.Version, OccurredAt: assignment.UpdatedAt, Payload: map[string]any{
			"assignmentId": assignment.AssignmentID, "version": assignment.Version, "tripId": assignment.TripID,
			"taskKey": assignment.TaskKey, "assigneePersonaId": assignment.AssigneePersonaID, "role": assignment.Role,
			"taskKind": assignment.TaskKind, "status": assignment.Status, "sourceRevisionNumber": assignment.SourceRevisionNumber,
			"updatedAt": assignment.UpdatedAt,
		}},
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
