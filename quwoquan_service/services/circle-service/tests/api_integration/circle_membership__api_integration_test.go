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
	membershipapp "quwoquan_service/services/circle-service/internal/application/circle/circle_membership"
	membershippersistence "quwoquan_service/services/circle-service/internal/infrastructure/circle/circle_membership/persistence"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
)

func TestCircleMembershipRealMongoTransactionReplayProjectionAndStream(t *testing.T) {
	cleanCollections(t)
	ctx := context.Background()
	seedMembershipCircle(t, "circle-membership", "persona-owner", 0)
	seedMembershipCircle(t, "circle-membership-other", "persona-other-owner", 0)

	forged := membershipRequest(t, http.MethodPost, "/circles/circle-membership/memberships", nil, "join-key-1", "")
	forged.Header.Set("X-Client-Persona-Id", "persona-member")
	forgedRecorder := httptest.NewRecorder()
	membershipGuard(http.MethodPost, "/circles/{circleId}/memberships", "JoinCircle").ServeHTTP(forgedRecorder, forged)
	if forgedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("forged actor header must fail closed: status=%d body=%s", forgedRecorder.Code, forgedRecorder.Body.String())
	}

	firstRecorder := executeMembershipCommand(t, http.MethodPost, "/circles/circle-membership/memberships", nil, "join-key-1", "", "persona-member", "JoinCircle")
	if firstRecorder.Code != http.StatusCreated {
		t.Fatalf("join failed: status=%d body=%s", firstRecorder.Code, firstRecorder.Body.String())
	}
	first := decodeBody(t, firstRecorder)
	if first["version"] != float64(1) || first["state"] != "active" || first["role"] != "member" || first["idempotentReplay"] != false {
		t.Fatalf("join result drift: %#v", first)
	}
	membershipID, _ := first["membershipId"].(string)
	if membershipID == "" {
		t.Fatal("join result has no membershipId")
	}

	selfRecorder := executeMembershipQuery(t, "/circles/circle-membership/memberships/self", "persona-member", "GetMyCircleMembership")
	if selfRecorder.Code != http.StatusOK {
		t.Fatalf("self membership failed: status=%d body=%s", selfRecorder.Code, selfRecorder.Body.String())
	}
	self := decodeBody(t, selfRecorder)
	if self["membershipId"] != membershipID || self["personaId"] != "persona-member" || self["version"] != float64(1) {
		t.Fatalf("self membership identity/version drift: %#v", self)
	}
	otherSelf := executeMembershipQuery(t, "/circles/circle-membership/memberships/self", "persona-other", "GetMyCircleMembership")
	if otherSelf.Code != http.StatusNotFound || decodeBody(t, otherSelf)["code"] != "CIRCLE.USER.membership_not_found" {
		t.Fatalf("cross-persona self membership must fail closed: status=%d body=%s", otherSelf.Code, otherSelf.Body.String())
	}

	replayRecorder := executeMembershipCommand(t, http.MethodPost, "/circles/circle-membership/memberships", nil, "join-key-1", "", "persona-member", "JoinCircle")
	if replayRecorder.Code != http.StatusCreated || decodeBody(t, replayRecorder)["idempotentReplay"] != true {
		t.Fatalf("join replay drift: status=%d body=%s", replayRecorder.Code, replayRecorder.Body.String())
	}

	conflictRecorder := executeMembershipCommand(t, http.MethodPost, "/circles/circle-membership-other/memberships", nil, "join-key-1", "", "persona-member", "JoinCircle")
	if conflictRecorder.Code != http.StatusConflict {
		t.Fatalf("idempotency conflict status=%d body=%s", conflictRecorder.Code, conflictRecorder.Body.String())
	}
	if code := decodeBody(t, conflictRecorder)["code"]; code != "CIRCLE.USER.membership_idempotency_conflict" {
		t.Fatalf("idempotency conflict code=%v", code)
	}

	for collection, want := range map[string]int64{
		"circle_memberships":                 1,
		"circle_membership_command_receipts": 1,
		"circle_membership_outbox":           1,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(ctx, bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}

	personaCircles := doRequest(t, http.MethodGet, "/personas/persona-member/circles?limit=10", nil)
	if personaCircles.Code != http.StatusOK {
		t.Fatalf("Persona Circle projection failed: status=%d body=%s", personaCircles.Code, personaCircles.Body.String())
	}
	personaCirclesBody := decodeBody(t, personaCircles)
	personaCircleItems, itemsOK := personaCirclesBody["items"].([]any)
	if !itemsOK || len(personaCircleItems) != 1 {
		t.Fatalf("Persona Circle projection drift: %#v", personaCirclesBody)
	}
	personaCircle := personaCircleItems[0].(map[string]any)
	if personaCircle["circleId"] != "circle-membership" || personaCircle["ownerPersonaId"] != "persona-owner" || personaCircle["state"] != "active" {
		t.Fatalf("Persona Circle projection leaked storage/aggregate wire names: %#v", personaCircle)
	}
	if _, leaked := personaCircle["_id"]; leaked {
		t.Fatalf("Persona Circle projection leaked Mongo identity: %#v", personaCircle)
	}

	leaveRecorder := executeMembershipCommand(t, http.MethodDelete, "/circles/circle-membership/memberships/self", nil, "leave-key-1", "", "persona-member", "LeaveCircle")
	if leaveRecorder.Code != http.StatusOK {
		t.Fatalf("leave failed: status=%d body=%s", leaveRecorder.Code, leaveRecorder.Body.String())
	}
	leave := decodeBody(t, leaveRecorder)
	if leave["version"] != float64(2) || leave["state"] != "left" {
		t.Fatalf("leave result drift: %#v", leave)
	}

	store := membershippersistence.NewMongoAggregateStore(mongoDB)
	countRelay := membershipapp.NewOutboxRelay(
		store, store,
		membershippersistence.NewMongoMemberCountProjector(mongoDB, redisRouter.Scene("general")),
		"circle-member-count-test",
	)
	if count, err := countRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("member-count drain count=%d err=%v", count, err)
	}
	assertCircleMemberCount(t, "circle-membership", 0)
	if inboxCount, err := mongoDB.Collection("circle_membership_projection_inbox").CountDocuments(ctx, bson.M{}); err != nil || inboxCount != 2 {
		t.Fatalf("membership projection inbox count=%d err=%v", inboxCount, err)
	}
	if _, err := mongoDB.Collection("circle_membership_projection_checkpoints").DeleteOne(ctx, bson.M{"_id": "circle-membership:circle-member-count-test"}); err != nil {
		t.Fatal(err)
	}
	if count, err := countRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("member-count replay count=%d err=%v", count, err)
	}
	assertCircleMemberCount(t, "circle-membership", 0)

	streamRelay := membershipapp.NewOutboxRelay(
		store, store, messaging.NewCircleMembershipStreamPublisher(redisRouter.Scene("general")),
		"circle-membership-stream-test",
	)
	if count, err := streamRelay.Drain(ctx, 10); err != nil || count != 2 {
		t.Fatalf("membership stream drain count=%d err=%v", count, err)
	}
	const group = "circle-membership-api-test"
	if err := redisRouter.Scene("general").XGroupCreateMkStream(ctx, messaging.CircleMembershipStream, group, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(ctx, group, "reader", map[string]string{messaging.CircleMembershipStream: ">"}, 10, 0)
	if err != nil || len(messages) != 2 {
		t.Fatalf("membership stream messages=%d err=%v", len(messages), err)
	}
	if messages[0].Values["aggregateType"] != "CircleMembership" || messages[0].Values["aggregateId"] != membershipID {
		t.Fatalf("membership stream envelope drift: %#v", messages[0].Values)
	}
}

func TestCircleMembershipOwnerInvariantAndModeratorRole(t *testing.T) {
	cleanCollections(t)
	seedMembershipCircle(t, "circle-moderated", "persona-owner", 0)

	ownerJoin := executeMembershipCommand(t, http.MethodPost, "/circles/circle-moderated/memberships", nil, "owner-join", "", "persona-owner", "JoinCircle")
	if ownerJoin.Code != http.StatusCreated || decodeBody(t, ownerJoin)["role"] != "owner" {
		t.Fatalf("owner membership drift: status=%d body=%s", ownerJoin.Code, ownerJoin.Body.String())
	}
	memberJoin := executeMembershipCommand(t, http.MethodPost, "/circles/circle-moderated/memberships", nil, "member-join", "", "persona-member", "JoinCircle")
	if memberJoin.Code != http.StatusCreated {
		t.Fatalf("member join failed: status=%d body=%s", memberJoin.Code, memberJoin.Body.String())
	}

	ownerLeave := executeMembershipCommand(t, http.MethodDelete, "/circles/circle-moderated/memberships/self", nil, "owner-leave", "", "persona-owner", "LeaveCircle")
	if ownerLeave.Code != http.StatusConflict || decodeBody(t, ownerLeave)["code"] != "CIRCLE.USER.membership_owner_cannot_leave" {
		t.Fatalf("owner leave invariant drift: status=%d body=%s", ownerLeave.Code, ownerLeave.Body.String())
	}

	roleBody := map[string]any{"role": "admin"}
	roleRecorder := executeMembershipCommand(t, http.MethodPatch, "/circles/circle-moderated/memberships/persona-member/role", roleBody, "role-key", "", "persona-owner", "UpdateCircleMembershipRole")
	if roleRecorder.Code != http.StatusOK {
		t.Fatalf("owner role update failed: status=%d body=%s", roleRecorder.Code, roleRecorder.Body.String())
	}
	role := decodeBody(t, roleRecorder)
	if role["version"] != float64(2) || role["role"] != "admin" {
		t.Fatalf("role result drift: %#v", role)
	}

	deniedBody := map[string]any{"role": "member"}
	deniedRecorder := executeMembershipCommand(t, http.MethodPatch, "/circles/circle-moderated/memberships/persona-member/role", deniedBody, "role-denied", "", "persona-outsider", "UpdateCircleMembershipRole")
	if deniedRecorder.Code != http.StatusForbidden || decodeBody(t, deniedRecorder)["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-moderator role update drift: status=%d body=%s", deniedRecorder.Code, deniedRecorder.Body.String())
	}

	roster := doRequest(t, http.MethodGet, "/circles/circle-moderated/memberships?limit=10", nil)
	if roster.Code != http.StatusOK || len(decodeBody(t, roster)["items"].([]any)) != 2 {
		t.Fatalf("CircleMembership roster drift: status=%d body=%s", roster.Code, roster.Body.String())
	}
}

func seedMembershipCircle(t *testing.T, circleID, ownerPersonaID string, memberCount int64) {
	t.Helper()
	now := time.Now().UTC()
	_, err := mongoDB.Collection("circles").InsertOne(context.Background(), bson.M{
		"_id": circleID, "name": circleID, "ownerId": ownerPersonaID,
		"status": "active", "joinPolicy": "open", "memberCount": memberCount,
		"createdAt": now, "updatedAt": now,
	})
	if err != nil {
		t.Fatal(err)
	}
}

func membershipGuard(method, pathTemplate, operationName string) http.Handler {
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(
		method,
		"CircleMembership",
	)
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_membership." + operationName,
			ContractGraphSHA256:  "circle-membership-api-integration",
			Method:               method, PathTemplate: pathTemplate,
			OperationKind: operationKind, MutationTarget: mutationTarget, InvariantTarget: invariantTarget,
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
}

func executeMembershipCommand(t *testing.T, method, path string, body any, idempotencyKey, ifMatch, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := membershipRequest(t, method, path, body, idempotencyKey, ifMatch)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/circles/{circleId}/memberships"
	if operationName == "LeaveCircle" {
		template += "/self"
	} else if operationName == "UpdateCircleMembershipRole" {
		template += "/{personaId}/role"
	}
	membershipGuard(method, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func executeMembershipQuery(t *testing.T, path, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := membershipRequest(t, http.MethodGet, path, nil, "query-"+personaID, "")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	membershipGuard(http.MethodGet, "/circles/{circleId}/memberships/self", operationName).ServeHTTP(recorder, request)
	return recorder
}

func membershipRequest(t *testing.T, method, path string, body any, idempotencyKey, ifMatch string) *http.Request {
	t.Helper()
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buffer)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("X-Request-Id", "request-"+idempotencyKey)
	request.Header.Set("X-Trace-Id", "trace-"+idempotencyKey)
	request.Header.Set("X-Client-Surface-Id", "circleDetail")
	request.Header.Set("X-Client-Session-Id", time.Now().UTC().Format(time.RFC3339Nano))
	if ifMatch != "" {
		request.Header.Set("If-Match", ifMatch)
	}
	return request
}

func assertCircleMemberCount(t *testing.T, circleID string, want int64) {
	t.Helper()
	var document struct {
		MemberCount int64 `bson:"memberCount"`
	}
	if err := mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&document); err != nil {
		t.Fatal(err)
	}
	if document.MemberCount != want {
		t.Fatalf("Circle %s memberCount=%d want=%d", circleID, document.MemberCount, want)
	}
}
