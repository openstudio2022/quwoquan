// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_plan_template_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

func TestTripPlanTemplateRejectsPrivateStayAndPreservesProfessionalAttribution(t *testing.T) {
	store := &templateStore{values: map[string]model.Template{}, receipts: map[string]ports.Receipt{}}
	service := application.NewService(store, templateReferences{}, templateIDs{}, func() time.Time { return time.Date(2026, 8, 2, 9, 0, 0, 0, time.UTC) })
	invalid := application.PutCommand{ActorPersonaID: "persona_guide", IdempotencyKey: "template-private-stay", Input: model.PutInput{Title: "杭州周末", DayCount: 2, Items: []model.Item{{TemplateItemID: "stay", DayOffset: 0, Kind: "stay", Title: "1208 房"}}, Attributions: []model.Attribution{}}}
	if _, err := service.Create(t.Context(), invalid); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("private stay err=%v", err)
	}
	valid := application.PutCommand{ActorPersonaID: "persona_guide", IdempotencyKey: "template-create", Input: model.PutInput{Title: "杭州周末", DayCount: 2, Items: []model.Item{
		{TemplateItemID: "stay", DayOffset: 0, OrderInDay: 0, Kind: "stay", AttributionIDs: []string{}},
		{TemplateItemID: "west_lake", DayOffset: 0, OrderInDay: 1, Kind: "sight", Title: "西湖", PublicPlaceRef: &model.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"}, AttributionIDs: []string{"guide_note"}},
	}, Attributions: []model.Attribution{{AttributionID: "guide_note", Kind: model.AttributionProfessionalCommentary, ReferenceObjectTypeRef: "content.Post", ReferenceObjectID: "post_note", AuthorPersonaID: "persona_guide", Title: "西湖讲解"}}}}
	created, err := service.Create(t.Context(), valid)
	if err != nil || created.Template.Version != 1 || created.Template.Items[0].PublicPlaceRef != nil || len(created.Template.AttributionPersonaIDs) != 1 {
		t.Fatalf("Create()=%+v err=%v", created, err)
	}
	replay, err := service.Create(t.Context(), valid)
	if err != nil || !replay.IdempotentReplay || len(store.events) != 1 {
		t.Fatalf("replay=%+v events=%d err=%v", replay, len(store.events), err)
	}
}

type templateReferences struct{}

func (templateReferences) ValidateTemplateAttributions(context.Context, string, []model.Attribution) error {
	return nil
}

type templateIDs struct{}

func (templateIDs) NewTripPlanTemplateID() (string, error) { return "tpt_1", nil }
func (templateIDs) NewEventID() (string, error)            { return "tev_template", nil }

type templateStore struct {
	values   map[string]model.Template
	receipts map[string]ports.Receipt
	events   []ports.OutboxEvent
}

func (store *templateStore) Get(_ context.Context, id string) (model.Template, error) {
	value, found := store.values[id]
	if !found {
		return model.Template{}, ports.ErrNotFound
	}
	return value, nil
}
func (store *templateStore) ListByOwner(_ context.Context, owner string) ([]model.Template, error) {
	result := []model.Template{}
	for _, value := range store.values {
		if value.OwnerPersonaID == owner {
			result = append(result, value)
		}
	}
	return result, nil
}
func (store *templateStore) FindReceipt(_ context.Context, key string) (ports.Receipt, bool, error) {
	value, found := store.receipts[key]
	return value, found, nil
}
func (store *templateStore) Commit(_ context.Context, commit ports.Commit) error {
	if receipt, found := store.receipts[commit.Receipt.IdempotencyKey]; found {
		if receipt.CommandDigest != commit.Receipt.CommandDigest {
			return ports.ErrIdempotencyConflict
		}
		return nil
	}
	current, found := store.values[commit.Template.TemplateID]
	if commit.ExpectedVersion == 0 && found || commit.ExpectedVersion > 0 && (!found || current.Version != commit.ExpectedVersion) {
		return ports.ErrCommitConflict
	}
	store.values[commit.Template.TemplateID] = commit.Template
	store.receipts[commit.Receipt.IdempotencyKey] = commit.Receipt
	store.events = append(store.events, commit.Event)
	return nil
}
