package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/circle-service/internal/infrastructure/messaging"
)

func TestCircleFileRealMongoTransactionReplayReaderBOLAAndStream(t *testing.T) {
	cleanCollections(t)
	t.Cleanup(func() { cleanCollections(t) })
	seedFilePolicy(t, "circle-file", "persona-owner", 8*1024)

	forged := groupRequest(t, http.MethodPost, "/v1/circles/circle-file/files", map[string]any{
		"name": "伪造目录", "fileType": "folder",
	})
	forged.Header.Set("Idempotency-Key", "file-forged")
	forged.Header.Set("X-Client-Persona-Id", "persona-owner")
	forgedRecorder := httptest.NewRecorder()
	fileGuard(http.MethodPost, "/v1/circles/{circleId}/files", "CreateCircleFile").ServeHTTP(forgedRecorder, forged)
	if forgedRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("forged CircleFile actor must fail closed: status=%d body=%s", forgedRecorder.Code, forgedRecorder.Body.String())
	}

	folderBody := map[string]any{"name": "旅行资料", "fileType": "folder"}
	folderCreated := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file/files", folderBody,
		"file-folder-create", "", "persona-owner", "CreateCircleFile",
	)
	if folderCreated.Code != http.StatusCreated {
		t.Fatalf("create CircleFile folder failed: status=%d body=%s", folderCreated.Code, folderCreated.Body.String())
	}
	folder := decodeBody(t, folderCreated)
	folderID, _ := folder["fileId"].(string)
	if folderID == "" || folder["version"] != float64(1) || folder["status"] != "active" || folder["idempotentReplay"] != false {
		t.Fatalf("CircleFile folder receipt drift: %#v", folder)
	}

	replay := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file/files", folderBody,
		"file-folder-create", "", "persona-owner", "CreateCircleFile",
	)
	if replay.Code != http.StatusCreated || decodeBody(t, replay)["idempotentReplay"] != true {
		t.Fatalf("CircleFile replay drift: status=%d body=%s", replay.Code, replay.Body.String())
	}
	conflict := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file/files",
		map[string]any{"name": "另一个目录", "fileType": "folder"},
		"file-folder-create", "", "persona-owner", "CreateCircleFile",
	)
	if conflict.Code != http.StatusConflict || decodeBody(t, conflict)["code"] != "CIRCLE.USER.file_idempotency_conflict" {
		t.Fatalf("CircleFile idempotency conflict drift: status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	fileCreated := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file/files",
		map[string]any{
			"parentFolderId": folderID, "name": "路线.pdf", "fileType": "file",
			"assetId": "asset-route-ready",
		},
		"file-create", "", "persona-owner", "CreateCircleFile",
	)
	if fileCreated.Code != http.StatusCreated {
		t.Fatalf("create CircleFile MediaAsset reference failed: status=%d body=%s", fileCreated.Code, fileCreated.Body.String())
	}
	fileReceipt := decodeBody(t, fileCreated)
	fileID, _ := fileReceipt["fileId"].(string)
	if fileID == "" || fileReceipt["version"] != float64(1) {
		t.Fatalf("CircleFile receipt drift: %#v", fileReceipt)
	}

	get := executeFileQuery(t, "/v1/circles/circle-file/files/"+fileID, "persona-owner", "GetCircleFile")
	if get.Code != http.StatusOK {
		t.Fatalf("get CircleFile failed: status=%d body=%s", get.Code, get.Body.String())
	}
	file := decodeBody(t, get)
	if file["fileId"] != fileID || file["assetId"] != "asset-route-ready" || file["mimeType"] != "application/pdf" || file["sizeBytes"] != float64(1024) {
		t.Fatalf("CircleFile Reader slice drift: %#v", file)
	}
	if _, leaked := file["objectKey"]; leaked {
		t.Fatalf("CircleFile leaked Media object storage key: %#v", file)
	}

	list := executeFileQuery(t, "/v1/circles/circle-file/files?parentFolderId="+folderID+"&limit=10", "persona-owner", "ListCircleFiles")
	if list.Code != http.StatusOK || len(decodeBody(t, list)["items"].([]any)) != 1 {
		t.Fatalf("list CircleFile failed: status=%d body=%s", list.Code, list.Body.String())
	}
	denied := executeFileQuery(t, "/v1/circles/circle-file/files?limit=10", "persona-outsider", "ListCircleFiles")
	if denied.Code != http.StatusForbidden || decodeBody(t, denied)["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("CircleFile BOLA must fail closed: status=%d body=%s", denied.Code, denied.Body.String())
	}

	updated := executeFileCommand(
		t, http.MethodPatch, "/v1/circles/circle-file/files/"+fileID,
		map[string]any{"name": "路线-v2.pdf"}, "file-update", `"1"`,
		"persona-owner", "UpdateCircleFile",
	)
	if updated.Code != http.StatusOK || decodeBody(t, updated)["version"] != float64(2) {
		t.Fatalf("update CircleFile failed: status=%d body=%s", updated.Code, updated.Body.String())
	}
	stale := executeFileCommand(
		t, http.MethodPatch, "/v1/circles/circle-file/files/"+fileID,
		map[string]any{"name": "stale.pdf"}, "file-update-stale", `"1"`,
		"persona-owner", "UpdateCircleFile",
	)
	if stale.Code != http.StatusConflict || decodeBody(t, stale)["code"] != "CIRCLE.USER.file_version_conflict" {
		t.Fatalf("CircleFile stale version must fail: status=%d body=%s", stale.Code, stale.Body.String())
	}

	deleted := executeFileCommand(
		t, http.MethodDelete, "/v1/circles/circle-file/files/"+fileID,
		nil, "file-delete", `"2"`, "persona-owner", "DeleteCircleFile",
	)
	if deleted.Code != http.StatusOK {
		t.Fatalf("delete CircleFile failed: status=%d body=%s", deleted.Code, deleted.Body.String())
	}
	deletedBody := decodeBody(t, deleted)
	if deletedBody["version"] != float64(3) || deletedBody["status"] != "deleted" {
		t.Fatalf("CircleFile delete receipt drift: %#v", deletedBody)
	}
	missing := executeFileQuery(t, "/v1/circles/circle-file/files/"+fileID, "persona-owner", "GetCircleFile")
	if missing.Code != http.StatusNotFound || decodeBody(t, missing)["code"] != "CIRCLE.USER.file_not_found" {
		t.Fatalf("deleted CircleFile must be absent from Reader: status=%d body=%s", missing.Code, missing.Body.String())
	}

	for collection, want := range map[string]int64{
		"circle_files": 2, "circle_files_command_receipts": 4, "circle_files_outbox": 4,
	} {
		count, err := mongoDB.Collection(collection).CountDocuments(context.Background(), bson.M{})
		if err != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, err)
		}
	}
	if count, err := fileStreamRelay.Drain(context.Background(), 10); err != nil || count != 4 {
		t.Fatalf("CircleFile stream drain count=%d err=%v", count, err)
	}
	const consumerGroup = "circle-file-api-test"
	if err := redisRouter.Scene("general").XGroupCreateMkStream(context.Background(), messaging.CircleFileStream, consumerGroup, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisRouter.Scene("general").XReadGroup(
		context.Background(), consumerGroup, "reader", map[string]string{messaging.CircleFileStream: ">"}, 10, 0,
	)
	if err != nil || len(messages) != 4 || messages[0].Values["aggregateType"] != "CircleFile" {
		t.Fatalf("CircleFile stream envelope drift: messages=%#v err=%v", messages, err)
	}
}

func TestCircleFileQuotaUsesAuthoritativeMediaAssetSize(t *testing.T) {
	cleanCollections(t)
	t.Cleanup(func() { cleanCollections(t) })
	seedFilePolicy(t, "circle-file-quota", "persona-owner", 1500)

	first := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file-quota/files",
		map[string]any{"name": "first.pdf", "fileType": "file", "assetId": "asset-first"},
		"quota-first", "", "persona-owner", "CreateCircleFile",
	)
	if first.Code != http.StatusCreated {
		t.Fatalf("first quota file failed: status=%d body=%s", first.Code, first.Body.String())
	}
	second := executeFileCommand(
		t, http.MethodPost, "/v1/circles/circle-file-quota/files",
		map[string]any{"name": "second.pdf", "fileType": "file", "assetId": "asset-second"},
		"quota-second", "", "persona-owner", "CreateCircleFile",
	)
	if second.Code != http.StatusRequestEntityTooLarge || decodeBody(t, second)["code"] != "CIRCLE.USER.storage_quota_exceeded" {
		t.Fatalf("CircleFile quota must use MediaAsset size: status=%d body=%s", second.Code, second.Body.String())
	}
}

func seedFilePolicy(t *testing.T, circleID, ownerPersonaID string, quotaBytes int64) {
	t.Helper()
	now := time.Now().UTC()
	if _, err := mongoDB.Collection("circles").InsertOne(context.Background(), bson.M{
		"_id": circleID, "name": circleID, "ownerId": ownerPersonaID,
		"status": "active", "storageQuotaBytes": quotaBytes,
		"createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := mongoDB.Collection("circle_memberships").InsertOne(context.Background(), bson.M{
		"_id": "file-membership-" + circleID, "version": 1,
		"circleId": circleID, "personaId": ownerPersonaID, "role": "owner", "state": "active",
		"createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
}

func executeFileCommand(
	t *testing.T,
	method string,
	path string,
	body any,
	idempotencyKey string,
	ifMatch string,
	personaID string,
	operationName string,
) *httptest.ResponseRecorder {
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
	template := "/v1/circles/{circleId}/files"
	if operationName == "UpdateCircleFile" || operationName == "DeleteCircleFile" {
		template += "/{fileId}"
	}
	fileGuard(method, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func executeFileQuery(t *testing.T, path, personaID, operationName string) *httptest.ResponseRecorder {
	t.Helper()
	request := groupRequest(t, http.MethodGet, path, nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	recorder := httptest.NewRecorder()
	template := "/v1/circles/{circleId}/files/{fileId}"
	if operationName == "ListCircleFiles" {
		template = "/v1/circles/{circleId}/files"
	}
	fileGuard(http.MethodGet, template, operationName).ServeHTTP(recorder, request)
	return recorder
}

func fileGuard(method, pathTemplate, operationName string) http.Handler {
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(
		method,
		"CircleFile",
	)
	return rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_file." + operationName,
			ContractGraphSHA256:  "circle-file-api-integration",
			Method:               method,
			PathTemplate:         pathTemplate,
			OperationKind:        operationKind,
			MutationTarget:       mutationTarget,
			InvariantTarget:      invariantTarget,
			AuthMode:             "required",
			ActorRequirement:     "persona",
			Principal:            "persona",
			CommercialStatus:     "ready",
			TimeoutMilliseconds:  1500,
		}}, method, pathTemplate,
	)(testHandler)
}
