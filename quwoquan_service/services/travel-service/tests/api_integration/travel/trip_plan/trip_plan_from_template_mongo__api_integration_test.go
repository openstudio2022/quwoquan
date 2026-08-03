// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package api_integration

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	tripapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/persistence"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/templatesource"
	revisiontransaction "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/adapters/inbound/transaction"
	revisionapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/application"
	revisionpersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/infrastructure/persistence"
	templateapplication "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/application"
	templatemodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	templatepersistence "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/infrastructure/persistence"
)

func TestCreateTripPlanFromTemplateMongoFreezesVersionAndAttributionInAtomicTripCommit(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "travel_trip_from_template_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	templateStore := templatepersistence.NewMongoStore(runtime.Database)
	if err := templateStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure TripPlanTemplate indexes: %v", err)
	}
	templateService := templateapplication.NewService(
		templateStore, templateAttributionAuthority{}, &templateAPIIDs{}, time.Now,
	)
	templateResult, err := templateService.Create(t.Context(), templateapplication.PutCommand{
		ActorPersonaID: "persona-guide", IdempotencyKey: "create-template",
		Input: templatemodel.PutInput{
			Title: "杭州周末", DayCount: 2,
			Items: []templatemodel.Item{
				{TemplateItemID: "stay", DayOffset: 0, OrderInDay: 0, Kind: "stay", AttributionIDs: []string{}},
				{TemplateItemID: "west-lake", DayOffset: 0, OrderInDay: 1, Kind: "sight", Title: "西湖", AttributionIDs: []string{"guide-note"}},
			},
			Attributions: []templatemodel.Attribution{{
				AttributionID: "guide-note", Kind: templatemodel.AttributionProfessionalCommentary,
				ReferenceObjectTypeRef: "content.Post", ReferenceObjectID: "post-guide",
				AuthorPersonaID: "persona-guide", Title: "西湖讲解",
			}},
		},
	})
	if err != nil {
		t.Fatalf("create template: %v", err)
	}

	revisionStore := revisionpersistence.NewMongoStore(runtime.Database)
	if err := revisionStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure TripPlanRevision indexes: %v", err)
	}
	tripStore := persistence.NewMongoStore(
		runtime.Database,
		revisiontransaction.NewAppender(revisionapplication.NewAppender(revisionStore)),
	)
	if err := tripStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure TripPlan indexes: %v", err)
	}
	tripService := tripapplication.NewService(
		tripStore, revisionapplication.NewReader(revisionStore), templatesource.NewStoreReader(templateStore),
		&mongoTestIDs{}, time.Now,
	)
	created, err := tripService.CreateFromTemplate(t.Context(), tripapplication.CreateFromTemplateCommand{
		ActorPersonaID: "persona-guide", IdempotencyKey: "create-trip-from-template",
		TemplateID: templateResult.Template.TemplateID,
	})
	if err != nil {
		t.Fatalf("CreateFromTemplate(): %v", err)
	}
	assertMongoCount(t, runtime.Database.Collection("trip_plans"), bson.M{
		"_id": created.TripID, "sourceTemplateId": templateResult.Template.TemplateID,
		"sourceTemplateVersion": int64(1), "sourcePostIds": "post-guide",
		"sourceAttributionPersonaIds": "persona-guide",
	}, 1)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_revisions"), bson.M{
		"tripId": created.TripID, "items.title": "住宿待确认",
	}, 1)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_command_receipts"), bson.M{
		"tripId": created.TripID,
	}, 1)
	assertMongoCount(t, runtime.Database.Collection("trip_plan_outbox"), bson.M{
		"aggregateId": created.TripID, "payloadJson.sourceTemplateVersion": int64(1),
	}, 1)
}

type templateAttributionAuthority struct{}

func (templateAttributionAuthority) ValidateTemplateAttributions(
	context.Context,
	string,
	[]templatemodel.Attribution,
) error {
	return nil
}

type templateAPIIDs struct{ value atomic.Int64 }

func (generator *templateAPIIDs) NewTripPlanTemplateID() (string, error) {
	return fmt.Sprintf("tpt_%d", generator.value.Add(1)), nil
}

func (generator *templateAPIIDs) NewEventID() (string, error) {
	return fmt.Sprintf("tve_template_%d", generator.value.Add(1)), nil
}
