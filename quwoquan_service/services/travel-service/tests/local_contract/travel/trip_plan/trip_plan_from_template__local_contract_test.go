// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	httpadapter "quwoquan_service/services/travel-service/internal/travel/trip_plan/adapters/inbound/http"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/templatesource"
	templatemodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	templateports "quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

func TestCreateTripPlanFromTemplateHTTPUsesGeneratedTypedRoute(t *testing.T) {
	store := newMemoryTripStore()
	service := application.NewService(store, store, &templateSourceStub{snapshot: application.TemplateSnapshot{
		TemplateID: "template-http", Version: 3, OwnerPersonaID: "persona-guide", Title: "西湖一日",
		Items:        []application.TemplateItem{{TemplateItemID: "west-lake", DayOffset: 0, OrderInDay: 0, Kind: model.ItemSight, Title: "西湖"}},
		Attributions: []model.SourceAttribution{},
	}}, &sequenceIDs{}, time.Now)
	mux := http.NewServeMux()
	httpadapter.NewHandler(service).RegisterRoutes(mux)
	request := newTripRequest(
		t, http.MethodPost, "/travel/templates/template-http/trips", `{}`,
		"travel.trip_plan.CreateTripPlanFromTemplate", "persona-guide", "template-http-create",
	)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var result struct {
		TripID string `json:"tripId"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil || result.TripID == "" {
		t.Fatalf("result=%+v err=%v", result, err)
	}
}

func TestCreateTripPlanFromTemplateFreezesPublicProvenanceAndDropsPrivateStayDetails(t *testing.T) {
	store := newMemoryTripStore()
	source := &templateSourceStub{snapshot: application.TemplateSnapshot{
		TemplateID: "template-hangzhou", Version: 7, OwnerPersonaID: "persona-guide", Title: "杭州周末",
		Items: []application.TemplateItem{
			{TemplateItemID: "stay", DayOffset: 0, OrderInDay: 0, Kind: model.ItemStay},
			{TemplateItemID: "west-lake", DayOffset: 0, OrderInDay: 1, Kind: model.ItemSight, Title: "西湖", PublicPlaceRef: &model.PlaceRef{ObjectTypeRef: "entity.Place", ObjectID: "west-lake"}},
		},
		Attributions: []model.SourceAttribution{
			{AttributionID: "guide-note", Kind: model.SourceAttributionProfessionalCommentary, PostID: "post-guide", AuthorPersonaID: "persona-guide", Title: "西湖讲解"},
			{AttributionID: "public-source", Kind: model.SourceAttributionPublicSource, PostID: "post-source", Title: "公开路线来源"},
		},
	}}
	service := application.NewService(
		store, store, source, &sequenceIDs{},
		func() time.Time { return time.Date(2026, 8, 2, 15, 0, 0, 0, time.UTC) },
	)
	command := application.CreateFromTemplateCommand{
		ActorPersonaID: "persona-guide", IdempotencyKey: "create-from-template",
		TemplateID: "template-hangzhou",
	}
	created, err := service.CreateFromTemplate(t.Context(), command)
	if err != nil {
		t.Fatalf("CreateFromTemplate(): %v", err)
	}
	plan, revision, err := service.Get(t.Context(), "persona-guide", created.TripID)
	if err != nil {
		t.Fatalf("Get(): %v", err)
	}
	if plan.SourceTemplateID != "template-hangzhou" || plan.SourceTemplateVersion != 7 ||
		len(plan.SourceAttributions) != 2 || len(plan.SourceAttributionPersonaIDs) != 1 ||
		len(plan.SourcePostIDs) != 2 {
		t.Fatalf("source provenance=%+v", plan)
	}
	if len(revision.Items) != 2 || revision.Items[0].Title != "住宿待确认" ||
		revision.Items[0].PlaceRef != nil || revision.Items[1].PlaceRef == nil {
		t.Fatalf("template items leaked private stay or lost public place: %+v", revision.Items)
	}
	replayed, err := service.CreateFromTemplate(t.Context(), command)
	if err != nil || !replayed.IdempotentReplay || replayed.TripID != created.TripID || source.calls != 1 {
		t.Fatalf("replay=%+v sourceCalls=%d err=%v", replayed, source.calls, err)
	}
	if store.events[0].Payload["sourceTemplateId"] != "template-hangzhou" ||
		store.events[0].Payload["sourceTemplateVersion"] != int64(7) {
		t.Fatalf("created event source=%+v", store.events[0].Payload)
	}
}

func TestTripPlanTemplateStoreReaderFailsClosedForForeignOrUnavailableTemplate(t *testing.T) {
	now := time.Date(2026, 8, 2, 15, 0, 0, 0, time.UTC)
	template, err := templatemodel.Create("template-1", "persona-owner", templatemodel.PutInput{
		Title: "杭州一日", DayCount: 1,
		Items:        []templatemodel.Item{{TemplateItemID: "west-lake", Kind: "sight", Title: "西湖", AttributionIDs: []string{}, DayOffset: 0, OrderInDay: 0}},
		Attributions: []templatemodel.Attribution{},
	}, now)
	if err != nil {
		t.Fatalf("template Create(): %v", err)
	}
	reader := templatesource.NewStoreReader(&templateStoreStub{template: template})
	if _, err := reader.GetOwnedActive(t.Context(), "persona-other", template.TemplateID); !errors.Is(err, application.ErrTemplatePermissionDenied) {
		t.Fatalf("foreign template err=%v", err)
	}
	if _, err := templatesource.NewStoreReader(&templateStoreStub{getErr: templateports.ErrNotFound}).GetOwnedActive(
		t.Context(), "persona-owner", template.TemplateID,
	); !errors.Is(err, application.ErrTemplateNotFound) {
		t.Fatalf("missing template err=%v", err)
	}
}

type templateSourceStub struct {
	snapshot application.TemplateSnapshot
	err      error
	calls    int
}

func (source *templateSourceStub) GetOwnedActive(context.Context, string, string) (application.TemplateSnapshot, error) {
	source.calls++
	return source.snapshot, source.err
}

type templateStoreStub struct {
	template templatemodel.Template
	getErr   error
}

func (store *templateStoreStub) Get(context.Context, string) (templatemodel.Template, error) {
	return store.template, store.getErr
}

func (*templateStoreStub) ListByOwner(context.Context, string) ([]templatemodel.Template, error) {
	return nil, nil
}

func (*templateStoreStub) FindReceipt(context.Context, string) (templateports.Receipt, bool, error) {
	return templateports.Receipt{}, false, nil
}

func (*templateStoreStub) Commit(context.Context, templateports.Commit) error {
	return nil
}

var _ templateports.Store = (*templateStoreStub)(nil)
var _ ports.Store = (*memoryTripStore)(nil)
