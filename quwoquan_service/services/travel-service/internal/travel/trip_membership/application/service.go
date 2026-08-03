package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/ports"
)

type Service struct {
	store   ports.Store
	trips   ports.TripAuthority
	sources ports.SourceAuthority
	ids     ports.IDGenerator
	now     func() time.Time
}

func NewService(
	store ports.Store,
	trips ports.TripAuthority,
	sources ports.SourceAuthority,
	ids ports.IDGenerator,
	now func() time.Time,
) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, trips: trips, sources: sources, ids: ids, now: now}
}

type PutCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	PersonaID       string
	ExpectedVersion int64
	Role            model.Role
	SourceKind      model.SourceKind
	SourceObjectRef *model.SourceRef
	SourceVersion   int64
}

type DepartCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	PersonaID       string
	ExpectedVersion int64
	Reason          string
}

func (service *Service) Put(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.PersonaID); err != nil {
		return ports.CommandResult{}, err
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	organizerID, err := service.organizer(ctx, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if strings.TrimSpace(command.ActorPersonaID) != organizerID {
		return ports.CommandResult{}, model.ErrPermissionDenied
	}
	if err := service.sources.ValidateMembershipSource(
		ctx, command.SourceKind, command.SourceObjectRef, command.SourceVersion, command.PersonaID,
	); err != nil {
		return ports.CommandResult{}, err
	}

	now := service.now().UTC()
	existing, getErr := service.store.Get(ctx, command.TripID, command.PersonaID)
	var membership model.Membership
	var expectedVersion int64
	switch {
	case errors.Is(getErr, ports.ErrNotFound):
		if command.ExpectedVersion != 0 {
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		membershipID, idErr := service.ids.NewTripMembershipID()
		if idErr != nil {
			return ports.CommandResult{}, idErr
		}
		membership, err = model.Create(model.PutInput{
			MembershipID: membershipID, TripID: command.TripID, PersonaID: command.PersonaID,
			OrganizerID: organizerID, Role: command.Role, SourceKind: command.SourceKind,
			SourceObjectRef: command.SourceObjectRef, SourceVersion: command.SourceVersion, Now: now,
		})
	case getErr != nil:
		return ports.CommandResult{}, getErr
	default:
		expectedVersion = existing.Version
		membership, err = existing.Put(
			command.ExpectedVersion, organizerID, command.Role, command.SourceKind,
			command.SourceObjectRef, command.SourceVersion, now,
		)
	}
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, expectedVersion, membership, "TripMembershipChanged", now)
}

func (service *Service) Depart(ctx context.Context, command DepartCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.PersonaID); err != nil ||
		strings.TrimSpace(command.Reason) == "" {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	organizerID, err := service.organizer(ctx, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	membership, err := service.store.Get(ctx, command.TripID, command.PersonaID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	next, err := membership.Depart(command.ExpectedVersion, command.ActorPersonaID, organizerID, now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, membership.Version, next, "TripMembershipChanged", now)
}

func (service *Service) List(ctx context.Context, actorPersonaID, tripID string) ([]model.Membership, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	tripID = strings.TrimSpace(tripID)
	if service == nil || service.store == nil || service.trips == nil || actorPersonaID == "" || tripID == "" {
		return nil, model.ErrInvalidArgument
	}
	organizerID, err := service.organizer(ctx, tripID)
	if err != nil {
		return nil, err
	}
	if actorPersonaID != organizerID {
		membership, getErr := service.store.Get(ctx, tripID, actorPersonaID)
		if getErr != nil {
			if errors.Is(getErr, ports.ErrNotFound) {
				return nil, model.ErrPermissionDenied
			}
			return nil, getErr
		}
		if membership.State != model.StateActive {
			return nil, model.ErrPermissionDenied
		}
	}
	return service.store.List(ctx, tripID)
}

// CanViewTrip is the minimal membership authority consumed by sibling Travel
// objects. The organizer is authorized by TripPlan even before an explicit
// organizer membership row exists; all other personas require active membership.
func (service *Service) CanViewTrip(ctx context.Context, actorPersonaID, tripID string) error {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	tripID = strings.TrimSpace(tripID)
	if service == nil || service.store == nil || service.trips == nil || actorPersonaID == "" || tripID == "" {
		return model.ErrInvalidArgument
	}
	organizerID, err := service.organizer(ctx, tripID)
	if err != nil {
		return err
	}
	if actorPersonaID == organizerID {
		return nil
	}
	membership, err := service.store.Get(ctx, tripID, actorPersonaID)
	if err != nil {
		if errors.Is(err, ports.ErrNotFound) {
			return model.ErrPermissionDenied
		}
		return err
	}
	if membership.State != model.StateActive {
		return model.ErrPermissionDenied
	}
	return nil
}

func (service *Service) ready(values ...string) error {
	if service == nil || service.store == nil || service.trips == nil || service.sources == nil || service.ids == nil {
		return model.ErrInvalidArgument
	}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return model.ErrInvalidArgument
		}
	}
	return nil
}

func (service *Service) organizer(ctx context.Context, tripID string) (string, error) {
	organizerID, err := service.trips.OrganizerPersonaID(ctx, strings.TrimSpace(tripID))
	if err != nil {
		return "", err
	}
	organizerID = strings.TrimSpace(organizerID)
	if organizerID == "" {
		return "", ports.ErrNotFound
	}
	return organizerID, nil
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
	membership model.Membership,
	eventType string,
	now time.Time,
) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Membership: membership}
	commit := ports.Commit{
		ExpectedVersion: expectedVersion,
		Membership:      membership,
		Receipt: ports.Receipt{
			IdempotencyKey: key, CommandDigest: digest, Result: result,
			ExpiresAt: now.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID: eventID, EventType: eventType, AggregateID: membership.MembershipID,
			AggregateVersion: membership.Version, OccurredAt: now,
			Payload: map[string]any{
				"membershipId": membership.MembershipID, "tripId": membership.TripID,
				"personaId": membership.PersonaID, "version": membership.Version,
				"role": membership.Role, "state": membership.State,
				"sourceVersion": membership.SourceVersion,
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
