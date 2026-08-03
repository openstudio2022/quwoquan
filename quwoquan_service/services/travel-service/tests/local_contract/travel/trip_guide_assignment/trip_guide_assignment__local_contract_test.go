// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_guide_assignment_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

func TestGuideTaskKeepsRoleAttributionAndIndependentLifecycle(t *testing.T) {
	store := &guideStore{values: map[string]model.Assignment{}, receipts: map[string]ports.Receipt{}}
	authority := guideAuthority{}
	service := application.NewService(store, authority, authority, application.NewPersonaAuthority(nil), guideIDs{}, time.Now)
	created, err := service.Put(t.Context(), application.PutCommand{ActorPersonaID: "persona_owner", IdempotencyKey: "guide-put", TripID: "trip_1", TaskKey: "meeting", Input: model.PutInput{AssigneePersonaID: "persona_assistant", Role: model.RoleAssistantGuide, TaskKind: model.TaskCollection, Title: "集合成员", SourceRevisionNumber: 2, AttributionKind: model.AttributionAdministrative, AttributionPersonaID: "persona_assistant"}})
	if err != nil || created.Assignment.Status != model.StatusAssigned || created.Assignment.Version != 1 {
		t.Fatalf("Put()=%+v err=%v", created, err)
	}
	accepted, err := service.Transition(t.Context(), application.TransitionCommand{ActorPersonaID: "persona_assistant", IdempotencyKey: "guide-accept", TripID: "trip_1", TaskKey: "meeting", ExpectedVersion: 1, TargetStatus: model.StatusAccepted})
	if err != nil || accepted.Assignment.Status != model.StatusAccepted {
		t.Fatalf("Transition()=%+v err=%v", accepted, err)
	}
	if _, err := service.Transition(t.Context(), application.TransitionCommand{ActorPersonaID: "persona_owner", IdempotencyKey: "guide-start-owner", TripID: "trip_1", TaskKey: "meeting", ExpectedVersion: 2, TargetStatus: model.StatusInProgress}); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("organizer impersonation err=%v", err)
	}
	if len(store.events) != 2 {
		t.Fatalf("events=%d", len(store.events))
	}
}

func TestLicensedGuideRequiresPublicPersonaReaderAndCannotBorrowQualification(t *testing.T) {
	service := application.NewService(&guideStore{values: map[string]model.Assignment{}, receipts: map[string]ports.Receipt{}}, guideAuthority{}, guideAuthority{}, application.NewPersonaAuthority(nil), guideIDs{}, time.Now)
	_, err := service.Put(t.Context(), application.PutCommand{ActorPersonaID: "persona_owner", IdempotencyKey: "licensed", TripID: "trip_1", TaskKey: "commentary", Input: model.PutInput{AssigneePersonaID: "persona_guide", Role: model.RoleLicensedGuide, TaskKind: model.TaskCommentary, Title: "专业讲解", SourceRevisionNumber: 2, AttributionKind: model.AttributionProfessionalCommentary, AttributionPersonaID: "persona_guide", PublicQualificationPersonaID: "persona_guide"}})
	if !errors.Is(err, ports.ErrReferenceUnavailable) {
		t.Fatalf("licensed guide without reader err=%v", err)
	}
	if _, err := model.Create("tga_2", "trip_1", "borrowed", "persona_owner", model.PutInput{AssigneePersonaID: "persona_guide", Role: model.RoleLicensedGuide, TaskKind: model.TaskCommentary, Title: "讲解", SourceRevisionNumber: 2, AttributionKind: model.AttributionProfessionalCommentary, AttributionPersonaID: "persona_guide", PublicQualificationPersonaID: "persona_other"}, time.Now()); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("borrowed qualification err=%v", err)
	}
}

type guideAuthority struct{}

func (guideAuthority) OrganizerPersonaID(context.Context, string) (string, error) {
	return "persona_owner", nil
}
func (guideAuthority) CanViewTrip(context.Context, string, string) error { return nil }

type guideIDs struct{}

func (guideIDs) NewTripGuideAssignmentID() (string, error) { return "tga_1", nil }
func (guideIDs) NewEventID() (string, error)               { return "tev_guide", nil }

type guideStore struct {
	values   map[string]model.Assignment
	receipts map[string]ports.Receipt
	events   []ports.OutboxEvent
}

func guideKey(tripID, taskKey string) string { return tripID + ":" + taskKey }
func (store *guideStore) Get(_ context.Context, tripID, taskKey string) (model.Assignment, error) {
	value, found := store.values[guideKey(tripID, taskKey)]
	if !found {
		return model.Assignment{}, ports.ErrNotFound
	}
	return value, nil
}
func (store *guideStore) ListByTrip(_ context.Context, tripID string) ([]model.Assignment, error) {
	result := []model.Assignment{}
	for _, value := range store.values {
		if value.TripID == tripID {
			result = append(result, value)
		}
	}
	return result, nil
}
func (store *guideStore) FindReceipt(_ context.Context, key string) (ports.Receipt, bool, error) {
	value, found := store.receipts[key]
	return value, found, nil
}
func (store *guideStore) Commit(_ context.Context, commit ports.Commit) error {
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	key := guideKey(commit.Assignment.TripID, commit.Assignment.TaskKey)
	current, found := store.values[key]
	if commit.ExpectedVersion == 0 && found || commit.ExpectedVersion > 0 && (!found || current.Version != commit.ExpectedVersion) {
		return ports.ErrCommitConflict
	}
	store.values[key] = commit.Assignment
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
