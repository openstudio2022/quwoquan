// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-001
// readiness_case: get-persona-management-summary-api
// readiness_case: get-persona-lifecycle-guard-api
// readiness_case: get-user-interest-profile-api
package api_integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestUserAccountPersonaManagementQueriesUsePostgresState(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const (
		ownerID   = "readiness_persona_management_owner"
		personaID = "readiness_persona_management_persona"
	)
	createTestProfile(t, ownerID, "readiness-persona-management-owner")
	createTestPersonaFull(
		t,
		personaID,
		ownerID,
		personaID,
		"Readiness Persona",
		"open",
		true,
		true,
	)

	summaryResponse := doRequest(
		t,
		http.MethodGet,
		"/user/personas/summary",
		"",
		authHeaders(ownerID),
	)
	if summaryResponse.Code != http.StatusOK {
		t.Fatalf("GetPersonaManagementSummary status=%d body=%s", summaryResponse.Code, summaryResponse.Body.String())
	}
	summary := parseJSON(t, summaryResponse)
	if summary["ownerUserId"] != ownerID || summary["totalCount"] != float64(1) || summary["activePersonaId"] != personaID {
		t.Fatalf("GetPersonaManagementSummary body=%#v", summary)
	}

	guardResponse := doRequest(
		t,
		http.MethodGet,
		"/user/personas/"+personaID+"/lifecycle-guard",
		"",
		authHeaders(ownerID),
	)
	if guardResponse.Code != http.StatusOK {
		t.Fatalf("GetPersonaLifecycleGuard status=%d body=%s", guardResponse.Code, guardResponse.Body.String())
	}
	guard := parseJSON(t, guardResponse)
	if guard["personaId"] != personaID || guard["allowed"] != false {
		t.Fatalf("GetPersonaLifecycleGuard body=%#v", guard)
	}
}

func TestUserAccountInterestProfileQueryUsesMongoProjection(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const ownerID = "readiness_interest_profile_owner"
	_, err := mongoDB.Collection("rm_user_profile_view").InsertOne(
		context.Background(),
		bson.M{
			"_id": ownerID,
			"interestProfile": bson.M{
				"topInterests": []bson.M{{
					"tagRef":    "travel",
					"dimension": "topic",
					"score":     0.9,
					"level":     5,
				}},
				"dimensionTops":     bson.M{"topic": []string{"travel"}},
				"lifecycleStage":    "active",
				"freshnessDays":     1,
				"decayHalfLifeDays": 30,
				"recomputedAt":      time.Now().UTC(),
			},
			"segments": []string{"travel_enthusiast"},
		},
	)
	if err != nil {
		t.Fatalf("seed interest profile projection: %v", err)
	}

	response := doRequest(
		t,
		http.MethodGet,
		"/users/"+ownerID+"/interest-profile",
		"",
		nil,
	)
	if response.Code != http.StatusOK {
		t.Fatalf("GetUserInterestProfile status=%d body=%s", response.Code, response.Body.String())
	}
	body := parseJSON(t, response)
	if body["userId"] != ownerID || body["lifecycleStage"] != "active" {
		t.Fatalf("GetUserInterestProfile body=%#v", body)
	}
	topInterests, ok := body["topInterests"].([]any)
	if !ok || len(topInterests) != 1 {
		t.Fatalf("GetUserInterestProfile topInterests=%#v", body["topInterests"])
	}
}
