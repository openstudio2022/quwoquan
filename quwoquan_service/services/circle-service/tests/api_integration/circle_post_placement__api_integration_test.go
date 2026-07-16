package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestCirclePostPlacementRealMongoTransactionAndTrustedActor(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	_, err := mongoDB.Collection("circles").InsertOne(ctx, bson.M{
		"_id": "circle-placement", "ownerId": "persona-moderator", "status": "active",
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, post := range []bson.M{
		{"_id": "post-placement-1", "ownerPersonaId": "persona-owner", "state": "published"},
		{"_id": "post-placement-2", "ownerPersonaId": "persona-owner", "state": "published"},
	} {
		if _, err := mongoDB.Collection("circle_post_owner_views").InsertOne(ctx, post); err != nil {
			t.Fatal(err)
		}
	}

	guard := rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_post_placement.PlacePostInCircle",
			ContractGraphSHA256:  "circle-placement-api-integration",
			Method:               http.MethodPost, PathTemplate: "/v1/circles/{circleId}/post-placements",
			OperationKind: "command", MutationTarget: "CirclePostPlacement", InvariantTarget: "CirclePostPlacement",
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}},
		http.MethodPost,
		"/v1/circles/{circleId}/post-placements",
	)(testHandler)

	forged := placementRequest(t, "post-placement-1", "placement-key-forged")
	forged.Header.Set("X-Client-Persona-Id", "persona-owner")
	forgedRecorder := httptest.NewRecorder()
	guard.ServeHTTP(forgedRecorder, forged)
	if forgedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("forged actor header must fail closed: status=%d body=%s", forgedRecorder.Code, forgedRecorder.Body.String())
	}

	first := placementRequest(t, "post-placement-1", "placement-key-1")
	first = first.WithContext(rtauth.WithPrincipal(first.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"},
	}))
	firstRecorder := httptest.NewRecorder()
	guard.ServeHTTP(firstRecorder, first)
	if firstRecorder.Code != http.StatusCreated {
		t.Fatalf("place failed: status=%d body=%s", firstRecorder.Code, firstRecorder.Body.String())
	}
	firstBody := decodeBody(t, firstRecorder)
	placementID, _ := firstBody["placementId"].(string)
	if placementID == "" || firstBody["version"] != float64(1) || firstBody["idempotentReplay"] != false {
		t.Fatalf("place response drift: %#v", firstBody)
	}

	replay := placementRequest(t, "post-placement-1", "placement-key-1")
	replay = replay.WithContext(rtauth.WithPrincipal(replay.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"},
	}))
	replayRecorder := httptest.NewRecorder()
	guard.ServeHTTP(replayRecorder, replay)
	if replayRecorder.Code != http.StatusCreated || decodeBody(t, replayRecorder)["idempotentReplay"] != true {
		t.Fatalf("idempotent replay drift: status=%d body=%s", replayRecorder.Code, replayRecorder.Body.String())
	}

	mismatch := placementRequest(t, "post-placement-2", "placement-key-1")
	mismatch = mismatch.WithContext(rtauth.WithPrincipal(mismatch.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-owner", PersonaID: "persona-owner"},
	}))
	mismatchRecorder := httptest.NewRecorder()
	guard.ServeHTTP(mismatchRecorder, mismatch)
	if mismatchRecorder.Code != http.StatusConflict {
		t.Fatalf("idempotency mismatch status=%d body=%s", mismatchRecorder.Code, mismatchRecorder.Body.String())
	}
	mismatchBody := decodeBody(t, mismatchRecorder)
	if mismatchBody["code"] != "CIRCLE.USER.placement_idempotency_conflict" {
		t.Fatalf("idempotency mismatch code drift: %#v", mismatchBody)
	}

	for collection, want := range map[string]int64{
		"circle_post_placements":                 1,
		"circle_post_placement_command_receipts": 1,
		"circle_post_placement_outbox":           1,
	} {
		count, countErr := mongoDB.Collection(collection).CountDocuments(ctx, bson.M{})
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
	var outbox bson.M
	if err := mongoDB.Collection("circle_post_placement_outbox").FindOne(ctx, bson.M{"aggregateId": placementID}).Decode(&outbox); err != nil {
		t.Fatal(err)
	}
	if outbox["eventType"] != "CirclePostPlaced" || outbox["aggregateVersion"] != int64(1) {
		t.Fatalf("outbox drift: %#v", outbox)
	}
}

func placementRequest(t *testing.T, postID, idempotencyKey string) *http.Request {
	t.Helper()
	body, err := json.Marshal(map[string]string{"postId": postID})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/v1/circles/circle-placement/post-placements", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("X-Request-Id", "request-"+idempotencyKey)
	request.Header.Set("X-Trace-Id", "trace-"+idempotencyKey)
	request.Header.Set("X-Client-Surface-Id", "homeFeed")
	request.Header.Set("X-Client-Session-Id", time.Now().UTC().Format(time.RFC3339Nano))
	return request
}
