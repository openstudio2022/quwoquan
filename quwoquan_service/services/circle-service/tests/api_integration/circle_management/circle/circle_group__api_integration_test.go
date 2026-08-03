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
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupmessaging "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/messaging"
	grouppersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
)

func TestCircleGroupRealMongoTransactionReplayReaderBOLAAndStream(t *testing.T) {
	cleanCollections(t)
	seedGroupCirclePolicy(t, "circle-group", "persona-owner", "persona-member")

	body := map[string]any{
		"groupType": "self_built", "name": "远行同好", "description": "一起出发",
		"visibility": "private", "joinPolicy": "apply_only",
		"storageEnabled": true, "noticeEnabled": true,
	}
	first := executeGroupCommand(t, http.MethodPost, "/circles/circle-group/groups", body, "group-create-1", "", "persona-member", "CreateCircleGroup")
	if first.Code != http.StatusCreated {
		t.Fatalf("create CircleGroup failed: status=%d body=%s", first.Code, first.Body.String())
	}
	created := decodeBody(t, first)
	groupID, _ := created["groupId"].(string)
	if groupID == "" || created["version"] != float64(1) || created["status"] != "active" || created["idempotentReplay"] != false {
		t.Fatalf("CircleGroup command receipt drift: %#v", created)
	}

	replay := executeGroupCommand(t, http.MethodPost, "/circles/circle-group/groups", body, "group-create-1", "", "persona-member", "CreateCircleGroup")
	if replay.Code != http.StatusCreated || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("CircleGroup replay drift: status=%d body=%s", replay.Code, replay.Body.String())
	}
	conflictingBody := map[string]any{
		"groupType": "self_built", "name": "另一个群", "description": "conflict",
		"visibility": "private", "joinPolicy": "apply_only",
		"storageEnabled": true, "noticeEnabled": true,
	}
	conflict := executeGroupCommand(t, http.MethodPost, "/circles/circle-group/groups", conflictingBody, "group-create-1", "", "persona-member", "CreateCircleGroup")
	if conflict.Code != http.StatusConflict || decodeBody(t, conflict)["code"] != "CIRCLE.USER.group_idempotency_conflict" {
		t.Fatalf("CircleGroup idempotency conflict drift: status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	for collection, want := range map[string]int64{
		"circle_groups": 1, "circle_group_command_receipts": 1, "circle_group_outbox": 1,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}

	get := executeGroupQuery(t, "/circles/circle-group/groups/"+groupID, "persona-member", "GetCircleGroup")
	if get.Code != http.StatusOK {
		t.Fatalf("get CircleGroup failed: status=%d body=%s", get.Code, get.Body.String())
	}
	group := decodeBody(t, get)
	if group["groupId"] != groupID || group["memberCount"] != float64(0) || group["version"] != float64(1) {
		t.Fatalf("CircleGroup Reader slice drift: %#v", group)
	}
	if _, leaked := group["id"]; leaked {
		t.Fatalf("CircleGroup Reader leaked Mongo identity: %#v", group)
	}
	if _, leaked := group["createdByPersonaId"]; leaked {
		t.Fatalf("CircleGroup Reader leaked audit identity: %#v", group)
	}

	denied := executeGroupQuery(t, "/circles/circle-group/groups/"+groupID, "persona-outsider", "GetCircleGroup")
	if denied.Code != http.StatusForbidden || decodeBody(t, denied)["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("CircleGroup BOLA must fail closed: status=%d body=%s", denied.Code, denied.Body.String())
	}

	// 归档要求 group owner 角色；owner membership 由 relay 投影，测试直接预置读模型。
	if _, err := mongoDB.Collection("circle_group_memberships").InsertOne(context.Background(), bson.M{
		"_id": "cgm-owner", "version": 1, "circleId": "circle-group", "groupId": groupID,
		"personaId": "persona-member", "role": "owner", "state": "active",
		"createdAt": time.Now().UTC(), "updatedAt": time.Now().UTC(),
	}); err != nil {
		t.Fatal(err)
	}
	withOwner := executeGroupQuery(t, "/circles/circle-group/groups/"+groupID, "persona-member", "GetCircleGroup")
	if withOwner.Code != http.StatusOK || decodeBody(t, withOwner)["memberCount"] != float64(1) {
		t.Fatalf("CircleGroup reader must count canonical active members: status=%d body=%s", withOwner.Code, withOwner.Body.String())
	}

	// 归档是命名迁移；已归档后的新 key 落 no-op receipt、不递增版本，同 key 重放。
	archived := executeGroupCommand(t, http.MethodDelete, "/circles/circle-group/groups/"+groupID, nil, "group-archive-1", "", "persona-member", "ArchiveCircleGroup")
	if archived.Code != http.StatusOK {
		t.Fatalf("archive CircleGroup failed: status=%d body=%s", archived.Code, archived.Body.String())
	}
	archivedBody := decodeBody(t, archived)
	if archivedBody["status"] != "archived" {
		t.Fatalf("CircleGroup archive receipt drift: %#v", archivedBody)
	}
	archivedVersion := archivedBody["version"]
	noop := executeGroupCommand(t, http.MethodDelete, "/circles/circle-group/groups/"+groupID, nil, "group-archive-noop", "", "persona-member", "ArchiveCircleGroup")
	if noop.Code != http.StatusOK {
		t.Fatalf("CircleGroup archive no-op failed: status=%d body=%s", noop.Code, noop.Body.String())
	}
	noopBody := decodeBody(t, noop)
	if noopBody["version"] != archivedVersion || noopBody["idempotentReplay"] != true {
		t.Fatalf("CircleGroup archive no-op must keep version and replay: %#v", noopBody)
	}
	noopReplay := executeGroupCommand(t, http.MethodDelete, "/circles/circle-group/groups/"+groupID, nil, "group-archive-noop", "", "persona-member", "ArchiveCircleGroup")
	if noopReplay.Code != http.StatusOK || decodeBody(t, noopReplay)["idempotentReplay"] != true {
		t.Fatalf("CircleGroup archive no-op replay drift: status=%d body=%s", noopReplay.Code, noopReplay.Body.String())
	}

	store := grouppersistence.NewMongoAggregateStore(mongoDB)
	streamRelay := groupapp.NewOutboxRelay(
		store, store, groupmessaging.NewCircleGroupStreamPublisher(circleMessageTransport), "circle-group-stream-test",
	)
	if count, err := streamRelay.Drain(context.Background(), 10); err != nil || count != 2 {
		t.Fatalf("CircleGroup stream drain count=%d err=%v", count, err)
	}
	const consumerGroup = "circle-group-api-test"
	if err := redisRouter.Scene("general").XGroupCreateMkStream(context.Background(), groupmessaging.CircleGroupStream, consumerGroup, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(context.Background(), consumerGroup, "reader", map[string]string{groupmessaging.CircleGroupStream: ">"}, 10, 0)
	if err != nil || len(messages) != 2 || messages[0].Values["aggregateType"] != "CircleGroup" {
		t.Fatalf("CircleGroup stream envelope drift: messages=%#v err=%v", messages, err)
	}
}

func seedGroupCirclePolicy(t *testing.T, circleID, ownerPersonaID, memberPersonaID string) {
	t.Helper()
	now := time.Now().UTC()
	if _, err := mongoDB.Collection("circles").InsertOne(context.Background(), bson.M{
		"_id": circleID, "status": "active", "ownerId": ownerPersonaID,
		"createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
	for _, membership := range []bson.M{
		{"_id": "cm-owner", "version": 1, "circleId": circleID, "personaId": ownerPersonaID, "role": "owner", "state": "active", "createdAt": now, "updatedAt": now},
		{"_id": "cm-member", "version": 1, "circleId": circleID, "personaId": memberPersonaID, "role": "member", "state": "active", "createdAt": now, "updatedAt": now},
	} {
		if _, err := mongoDB.Collection("circle_memberships").InsertOne(context.Background(), membership); err != nil {
			t.Fatal(err)
		}
	}
}

func executeGroupCommand(t *testing.T, method, path string, body any, idempotencyKey, ifMatch, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupRequest(t, method, path, body)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	if ifMatch != "" {
		request.Header.Set("If-Match", ifMatch)
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/circles/{circleId}/groups"
	if operationName == "UpdateCircleGroup" || operationName == "ArchiveCircleGroup" {
		template += "/{groupId}"
	}
	groupGuard(method, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func executeGroupQuery(t *testing.T, path, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupRequest(t, http.MethodGet, path, nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/circles/{circleId}/groups/{groupId}"
	if operationName == "ListCircleGroups" {
		template = "/circles/{circleId}/groups"
	} else if operationName == "SearchCircleGroups" {
		template = "/circles/{circleId}/groups/search"
	}
	groupGuard(http.MethodGet, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func groupGuard(method, pathTemplate, operationName string) http.Handler {
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(
		method,
		"CircleGroup",
	)
	versionPrecondition := ""
	if operationName == "UpdateCircleGroup" {
		versionPrecondition = "if_match"
	}
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_group." + operationName,
			ContractGraphSHA256:  "circle-group-api-integration", Method: method, PathTemplate: pathTemplate,
			OperationKind: operationKind, MutationTarget: mutationTarget, InvariantTarget: invariantTarget,
			VersionPrecondition: versionPrecondition,
			AuthMode:            "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
}

func groupRequest(t *testing.T, method, path string, body any) *http.Request {
	t.Helper()
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buffer)
	request.Header.Set("Content-Type", "application/json")
	return request
}
