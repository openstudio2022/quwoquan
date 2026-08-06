// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001
// readiness_case: create-gathering-plan-api
// readiness_case: propose-gathering-plan-api
// readiness_case: commit-gathering-plan-proposal-api
// readiness_case: get-gathering-plan-api
// readiness_case: list-gathering-plan-revisions-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	rterr "quwoquan_service/runtime/errors"
	planhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/adapters/inbound/http"
	planapp "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	planports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
	planpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

func TestGatheringPlanHTTPCommitsMongoOwnerStateReceiptAndEventLog(t *testing.T) {
	database := testsupport.StartRealMongo(t, "gathering_plan_object_api")
	ctx := context.Background()
	store := planpersistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	reader := planpersistence.NewMongoGatheringPlanReader(database)
	authority := apiAuthority{}
	handler := planhttp.NewHandler(
		planapp.NewGatheringPlanCommandFacet(store, authority),
		planapp.NewGatheringPlanQueryFacet(reader, authority),
		func(err error) error {
			return rterr.NewInvalidArgument(rterr.ModuleCircle, "GatheringPlan test request failed", err.Error())
		},
	)
	mux := http.NewServeMux()
	handler.Register(mux)

	create := testsupport.Request(t, http.MethodPost, "/gatherings/gathering-plan-api/plan", map[string]any{
		"items": []map[string]any{{
			"itemId": "agenda-1", "kind": "agenda", "order": 0,
			"agenda": map[string]any{"content": "集合与出发"}, "sourceRefs": []any{},
		}},
		"acknowledgementPolicy":     map[string]any{"mode": "none"},
		"affectedParticipationRefs": []any{},
	}, "circle.gathering_plan.CreateGatheringPlan", "host-plan-api", "plan-create-1")
	createRecorder := httptest.NewRecorder()
	mux.ServeHTTP(createRecorder, create)
	if createRecorder.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", createRecorder.Code, createRecorder.Body.String())
	}
	created := decodeResponse(t, createRecorder)
	planID, _ := created["planId"].(string)
	baseRevisionID, _ := created["currentRevisionId"].(string)
	baseRevisionDigest, _ := created["currentRevisionDigest"].(string)
	if planID == "" || baseRevisionID == "" || baseRevisionDigest == "" {
		t.Fatalf("create response lacks typed identity/digest: %#v", created)
	}

	propose := testsupport.Request(t, http.MethodPost, "/gathering-plans/"+planID+"/proposals", map[string]any{
		"expectedPlanVersion": 1, "baseRevisionId": baseRevisionID,
		"baseRevisionNumber": 1, "baseRevisionDigest": baseRevisionDigest,
		"items": []map[string]any{{
			"itemId": "task-1", "kind": "task", "order": 0,
			"task": map[string]any{"content": "确认补给", "completed": false}, "sourceRefs": []any{},
		}},
		"acknowledgementPolicy": map[string]any{"mode": "affected_participations"},
		"affectedParticipationRefs": []map[string]any{{
			"gatheringId": "gathering-plan-api", "personaId": "participant-plan-api",
		}},
	}, "circle.gathering_plan.ProposeGatheringPlan", "participant-plan-api", "plan-propose-1")
	proposeRecorder := httptest.NewRecorder()
	mux.ServeHTTP(proposeRecorder, propose)
	if proposeRecorder.Code != http.StatusOK {
		t.Fatalf("propose status=%d body=%s", proposeRecorder.Code, proposeRecorder.Body.String())
	}
	proposed := decodeResponse(t, proposeRecorder)
	proposalID, _ := proposed["proposalId"].(string)
	proposalDigest, _ := proposed["proposalDigest"].(string)
	if proposalID == "" || proposalDigest == "" || proposed["planVersion"] != float64(2) {
		t.Fatalf("propose response invalid: %#v", proposed)
	}

	commit := testsupport.Request(t, http.MethodPost, "/gathering-plans/"+planID+"/commit", map[string]any{
		"proposalId": proposalID, "expectedPlanVersion": 2,
		"expectedProposalDigest": proposalDigest, "expectedBaseRevisionDigest": baseRevisionDigest,
	}, "circle.gathering_plan.CommitGatheringPlanProposal", "host-plan-api", "plan-commit-1")
	commitRecorder := httptest.NewRecorder()
	mux.ServeHTTP(commitRecorder, commit)
	if commitRecorder.Code != http.StatusOK {
		t.Fatalf("commit status=%d body=%s", commitRecorder.Code, commitRecorder.Body.String())
	}
	committed := decodeResponse(t, commitRecorder)
	if committed["planVersion"] != float64(3) || committed["currentRevisionNumber"] != float64(2) {
		t.Fatalf("commit response invalid: %#v", committed)
	}

	get := testsupport.Request(t, http.MethodGet, "/gatherings/gathering-plan-api/plan", nil,
		"circle.gathering_plan.GetGatheringPlan", "participant-plan-api", "plan-get-1")
	getRecorder := httptest.NewRecorder()
	mux.ServeHTTP(getRecorder, get)
	if getRecorder.Code != http.StatusOK || decodeResponse(t, getRecorder)["id"] != planID {
		t.Fatalf("get status=%d body=%s", getRecorder.Code, getRecorder.Body.String())
	}

	list := testsupport.Request(t, http.MethodGet, "/gathering-plans/"+planID+"/revisions?limit=20", nil,
		"circle.gathering_plan.ListGatheringPlanRevisions", "participant-plan-api", "plan-list-1")
	listRecorder := httptest.NewRecorder()
	mux.ServeHTTP(listRecorder, list)
	listed := decodeResponse(t, listRecorder)
	items, _ := listed["items"].([]any)
	if listRecorder.Code != http.StatusOK || len(items) != 2 {
		t.Fatalf("list status=%d body=%s", listRecorder.Code, listRecorder.Body.String())
	}

	testsupport.AssertCollectionCount(t, database, "gathering_plans", 1)
	testsupport.AssertCollectionCount(t, database, "gathering_plan_command_receipts", 3)
	testsupport.AssertCollectionCount(t, database, "gathering_plan_event_log", 3)
	var persisted struct {
		Revisions []bson.M `bson:"revisions"`
		Proposals []bson.M `bson:"proposals"`
	}
	if err := database.Collection("gathering_plans").FindOne(ctx, bson.M{"_id": planID}).Decode(&persisted); err != nil {
		t.Fatal(err)
	}
	if len(persisted.Revisions) != 2 || len(persisted.Proposals) != 1 {
		t.Fatalf("owner state is not atomic/complete: revisions=%d proposals=%d", len(persisted.Revisions), len(persisted.Proposals))
	}
}

type apiAuthority struct{}

func (apiAuthority) ReadGatheringAuthority(_ context.Context, gatheringID, actor string) (planports.GatheringAuthority, error) {
	return planports.GatheringAuthority{
		GatheringID: gatheringID, Exists: true, CollaborationOpen: true,
		CurrentHost: actor == "host-plan-api", ActiveParticipation: actor == "participant-plan-api",
	}, nil
}

func decodeResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode response: %v body=%s", err, recorder.Body.String())
	}
	return value
}
