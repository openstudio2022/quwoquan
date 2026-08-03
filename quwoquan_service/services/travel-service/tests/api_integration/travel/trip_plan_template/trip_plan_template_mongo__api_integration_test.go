// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_plan_template_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/infrastructure/persistence"
	travelsupport "quwoquan_service/services/travel-service/tests/support"
)

func TestTripPlanTemplateMongoCommitsSanitizedTemplateReceiptAndOutbox(t *testing.T) {
	database := travelsupport.StartRealMongo(t, "travel_trip_template_api_integration")
	store := persistence.NewMongoStore(database)
	if err := store.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	service := application.NewService(store, templateReferences{}, templateIDs{}, time.Now)
	result, err := service.Create(t.Context(), application.PutCommand{ActorPersonaID: "persona_guide", IdempotencyKey: "template-create", Input: model.PutInput{Title: "西湖周末", DayCount: 2, Items: []model.Item{{TemplateItemID: "stay", DayOffset: 0, OrderInDay: 0, Kind: "stay", AttributionIDs: []string{}}, {TemplateItemID: "sight", DayOffset: 0, OrderInDay: 1, Kind: "sight", Title: "西湖", PublicPlaceRef: &model.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west_lake"}, AttributionIDs: []string{}}}, Attributions: []model.Attribution{}}})
	if err != nil || result.Template.Version != 1 {
		t.Fatalf("Create()=%+v err=%v", result, err)
	}
	travelsupport.Count(t, database.Collection("trip_plan_templates"), bson.M{"ownerPersonaId": "persona_guide"}, 1)
	travelsupport.Count(t, database.Collection("trip_plan_template_command_receipts"), bson.M{}, 1)
	travelsupport.Count(t, database.Collection("trip_plan_template_outbox"), bson.M{}, 1)
}

type templateReferences struct{}

func (templateReferences) ValidateTemplateAttributions(context.Context, string, []model.Attribution) error {
	return nil
}

type templateIDs struct{}

func (templateIDs) NewTripPlanTemplateID() (string, error) { return "tpt_1", nil }
func (templateIDs) NewEventID() (string, error)            { return "tev_template", nil }
