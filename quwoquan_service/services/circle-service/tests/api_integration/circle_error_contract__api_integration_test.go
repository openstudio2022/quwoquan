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

// seedActiveCircleMembership 预置 file 权限校验用的 active membership 读模型。
func seedActiveCircleMembership(t *testing.T, circleID, personaID, role string) {
	t.Helper()
	now := time.Now().UTC()
	if _, err := mongoDB.Collection("circle_memberships").InsertOne(context.Background(), bson.M{
		"_id": "cm-" + circleID + "-" + personaID, "version": 1,
		"circleId": circleID, "personaId": personaID, "role": role, "state": "active",
		"createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}
}

func executeFileRequest(t *testing.T, method, path string, body any, idempotencyKey, personaID, operationName, pathTemplate string) *httptest.ResponseRecorder {
	t.Helper()
	var buffer bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buffer).Encode(body); err != nil {
			t.Fatal(err)
		}
	}
	request := httptest.NewRequest(method, path, &buffer)
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-" + personaID, PersonaID: personaID},
	}))
	operationKind, mutationTarget, invariantTarget := generatedTestOperationSemantics(method, "CircleFile")
	recorder := httptest.NewRecorder()
	guard := rtauth.RequireGeneratedOperationAuthorizationForRoute(
		[]rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "circle.circle_file." + operationName,
			ContractGraphSHA256:  "circle-file-api-integration",
			Method:               method, PathTemplate: pathTemplate,
			OperationKind: operationKind, MutationTarget: mutationTarget, InvariantTarget: invariantTarget,
			AuthMode: "required", ActorRequirement: "persona", Principal: "persona",
			CommercialStatus: "ready", TimeoutMilliseconds: 1500,
		}}, method, pathTemplate,
	)(testHandler)
	guard.ServeHTTP(recorder, request)
	return recorder
}

func TestGetCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodGet, "/circles/nonexistent_id_000", nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d", rec.Code)
	}
}

func TestArchiveCircle_NotFound(t *testing.T) {
	defer cleanCollections(t)

	rec := executeCircleCommand(t, http.MethodDelete, "/circles/nonexistent_id_000", nil,
		"circle-archive-missing", "persona-circle-owner", "ArchiveCircle", "/circles/{circleId}")
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	if decodeBody(t, rec)["code"] != "CIRCLE.USER.not_found" {
		t.Errorf("expected CIRCLE.USER.not_found")
	}
}

func TestGetFile_NotFound(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "文件不存在测试", "persona-file-owner")
	seedActiveCircleMembership(t, circleID, "persona-file-owner", "owner")

	rec := executeFileRequest(t, http.MethodGet, "/circles/"+circleID+"/files/nonexistent_file", nil,
		"", "persona-file-owner", "GetCircleFile", "/circles/{circleId}/files/{fileId}")
	if rec.Code != http.StatusNotFound {
		t.Errorf("expected 404, got %d: %s", rec.Code, rec.Body.String())
	}
	if decodeBody(t, rec)["code"] != "CIRCLE.USER.file_not_found" {
		t.Errorf("expected CIRCLE.USER.file_not_found")
	}
}

func TestCreateCircle_MissingName(t *testing.T) {
	defer cleanCollections(t)

	rec := executeCircleCommand(t, http.MethodPost, "/circles", map[string]any{
		"category": "interest",
	}, "circle-create-missing-name", "persona-circle-owner", "CreateCircle", "/circles")
	if rec.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	if decodeBody(t, rec)["code"] != "CIRCLE.USER.invalid_argument" {
		t.Errorf("expected CIRCLE.USER.invalid_argument")
	}
}

// 文件尺寸真相源是权威 MediaAsset；配额约束在 CircleFile 事务内串行化。
func TestFileQuotaExceededUsesAuthoritativeAssetSize(t *testing.T) {
	cleanCollections(t)
	defer cleanCollections(t)

	circleID := createTestCircleAs(t, "配额超限测试", "persona-file-owner")
	seedActiveCircleMembership(t, circleID, "persona-file-owner", "owner")

	// readyMediaAssetReader 从 asset id 后缀解析权威尺寸：默认配额 1GB，2GB 超限。
	rec := executeFileRequest(t, http.MethodPost, "/circles/"+circleID+"/files", map[string]any{
		"name":     "huge.bin",
		"fileType": "file",
		"assetId":  "asset-bytes-2147483648",
	}, "file-create-over-quota", "persona-file-owner", "CreateCircleFile", "/circles/{circleId}/files")
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Errorf("expected 413, got %d: %s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	if body["code"] != "CIRCLE.USER.storage_quota_exceeded" {
		t.Errorf("expected CIRCLE.USER.storage_quota_exceeded, got %v", body["code"])
	}
}
