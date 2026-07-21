package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/content-service/internal/application/identity"
)

func TestMediaAssetReferenceUsesRealStoreAndServiceScopedAuthorization(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	ownerPersonaID := identity.AnonymousFallbackSubAccountID

	initRequest := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads:init",
		strings.NewReader(`{"mediaType":"image","contentType":"image/png","fileSize":2048,"expectedSha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`),
	)
	initRequest.Header.Set("Content-Type", "application/json")
	initRequest.Header.Set("X-Client-User-Id", ownerPersonaID)
	initRequest.Header.Set("X-Client-Sub-Account-Id", ownerPersonaID)
	initRequest.Header.Set("Idempotency-Key", "media-reference-init")
	initRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(initRecorder, initRequest)
	if initRecorder.Code != http.StatusOK {
		t.Fatalf("init MediaUploadSession failed: status=%d body=%s", initRecorder.Code, initRecorder.Body.String())
	}
	var initialized map[string]any
	if err := json.Unmarshal(initRecorder.Body.Bytes(), &initialized); err != nil {
		t.Fatal(err)
	}
	sessionID, _ := initialized["sessionId"].(string)
	if sessionID == "" {
		t.Fatalf("MediaUploadSession result has no sessionId: %#v", initialized)
	}

	completeRequest := httptest.NewRequest(
		http.MethodPost,
		"/content/media/uploads/"+sessionID+":complete",
		strings.NewReader(`{"accessPolicy":"owner_only"}`),
	)
	completeRequest.Header.Set("Content-Type", "application/json")
	completeRequest.Header.Set("X-Client-User-Id", ownerPersonaID)
	completeRequest.Header.Set("X-Client-Sub-Account-Id", ownerPersonaID)
	completeRequest.Header.Set("Idempotency-Key", "media-reference-complete")
	completeRecorder := httptest.NewRecorder()
	testHandler.ServeHTTP(completeRecorder, completeRequest)
	if completeRecorder.Code != http.StatusOK {
		t.Fatalf("complete MediaUploadSession failed: status=%d body=%s", completeRecorder.Code, completeRecorder.Body.String())
	}
	var completed map[string]any
	if err := json.Unmarshal(completeRecorder.Body.Bytes(), &completed); err != nil {
		t.Fatal(err)
	}
	assetID, _ := completed["assetId"].(string)
	if assetID == "" {
		t.Fatalf("completed MediaUploadSession has no assetId: %#v", completed)
	}
	performMediaCommand(
		t,
		http.MethodPost,
		"/internal/content/media/"+assetID+":processing-result",
		fmt.Sprintf(`{
			"processingStatus":"ready",
			"processorProfile":"content_image_normalization_v1",
			"imageWidth":540,
			"imageHeight":960,
			"imageDeliveryContentType":"image/png",
			"imageNormalizedObjectKey":"media/processed/image/%s/v2/source.png",
			"imagePublicSliceKey":"media/image/s/asset/%s/v2/source.png",
			"imageDominantColor":"#1A2B3C",
			"imageLqip":"data:image/jpeg;base64,/9j/2Q==",
			"imageContentProfile":"alpha_graphic",
			"imageDerivativePolicyVersion":1
		}`, assetID, assetID),
		ownerPersonaID,
		"media-reference-processing-ready",
	)
	var persisted struct {
		OwnerID          string `bson:"ownerId"`
		ProcessingStatus string `bson:"processingStatus"`
	}
	if err := mongoDB.Collection("media_assets").FindOne(
		context.Background(), bson.M{"_id": assetID},
	).Decode(&persisted); err != nil {
		t.Fatalf("load persisted MediaAsset: %v", err)
	}
	if persisted.OwnerID != ownerPersonaID || persisted.ProcessingStatus != "ready" {
		t.Fatalf("persisted MediaAsset owner/status drift: %#v", persisted)
	}

	secured := contentSecuredHandler(t)
	serviceToken := mediaReferenceServiceToken(t, []string{"content.media.reference.read"})
	request := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":reference?ownerPersonaId="+ownerPersonaID,
		nil,
	)
	request.Header.Set("Authorization", "Bearer "+serviceToken)
	recorder := httptest.NewRecorder()
	secured.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("MediaAsset reference failed: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var reference map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &reference); err != nil {
		t.Fatal(err)
	}
	if reference["assetId"] != assetID || reference["ownerPersonaId"] != ownerPersonaID ||
		reference["processingStatus"] != "ready" || reference["contentType"] != "image/png" ||
		reference["fileSize"] != float64(2048) {
		t.Fatalf("MediaAsset reference slice drift: %#v", reference)
	}
	for _, forbidden := range []string{"objectKey", "cdnUrl", "sha256", "accessPolicy"} {
		if _, leaked := reference[forbidden]; leaked {
			t.Fatalf("MediaAsset reference leaked %s: %#v", forbidden, reference)
		}
	}

	deliveryToken := mediaReferenceServiceToken(t, []string{"content.media.delivery.read"})
	deliveryRequest := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":delivery-reference?ownerPersonaId="+ownerPersonaID,
		nil,
	)
	deliveryRequest.Header.Set("Authorization", "Bearer "+deliveryToken)
	deliveryRecorder := httptest.NewRecorder()
	secured.ServeHTTP(deliveryRecorder, deliveryRequest)
	if deliveryRecorder.Code != http.StatusOK {
		t.Fatalf("MediaAsset delivery reference failed: status=%d body=%s", deliveryRecorder.Code, deliveryRecorder.Body.String())
	}
	var delivery map[string]any
	if err := json.Unmarshal(deliveryRecorder.Body.Bytes(), &delivery); err != nil {
		t.Fatal(err)
	}
	if delivery["assetId"] != assetID || delivery["ownerPersonaId"] != ownerPersonaID ||
		delivery["processingStatus"] != "ready" || delivery["mediaType"] != "image" ||
		delivery["contentType"] != "image/png" || delivery["fileSize"] != float64(2048) ||
		strings.TrimSpace(fmt.Sprint(delivery["cdnUrl"])) == "" {
		t.Fatalf("MediaAsset delivery reference slice drift: %#v", delivery)
	}
	for _, forbidden := range []string{"objectKey", "sha256", "accessPolicy"} {
		if _, leaked := delivery[forbidden]; leaked {
			t.Fatalf("MediaAsset delivery reference leaked %s: %#v", forbidden, delivery)
		}
	}
	deliveryWrongScope := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":delivery-reference?ownerPersonaId="+ownerPersonaID,
		nil,
	)
	deliveryWrongScope.Header.Set("Authorization", "Bearer "+serviceToken)
	deliveryWrongScopeRecorder := httptest.NewRecorder()
	secured.ServeHTTP(deliveryWrongScopeRecorder, deliveryWrongScope)
	if deliveryWrongScopeRecorder.Code != http.StatusForbidden {
		t.Fatalf("reference-only scope must not read delivery URL: status=%d body=%s", deliveryWrongScopeRecorder.Code, deliveryWrongScopeRecorder.Body.String())
	}

	wrongOwner := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":reference?ownerPersonaId=persona-other",
		nil,
	)
	wrongOwner.Header.Set("Authorization", "Bearer "+serviceToken)
	wrongOwnerRecorder := httptest.NewRecorder()
	secured.ServeHTTP(wrongOwnerRecorder, wrongOwner)
	if wrongOwnerRecorder.Code != http.StatusNotFound {
		t.Fatalf("cross-owner MediaAsset reference must fail closed: status=%d body=%s", wrongOwnerRecorder.Code, wrongOwnerRecorder.Body.String())
	}

	withoutCredential := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":reference?ownerPersonaId="+ownerPersonaID,
		nil,
	)
	withoutCredentialRecorder := httptest.NewRecorder()
	secured.ServeHTTP(withoutCredentialRecorder, withoutCredential)
	if withoutCredentialRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("missing service credential must fail: status=%d body=%s", withoutCredentialRecorder.Code, withoutCredentialRecorder.Body.String())
	}

	wrongScope := httptest.NewRequest(
		http.MethodGet,
		"/internal/content/media/"+assetID+":reference?ownerPersonaId="+ownerPersonaID,
		nil,
	)
	wrongScope.Header.Set("Authorization", "Bearer "+mediaReferenceServiceToken(t, []string{"content.media.process"}))
	wrongScopeRecorder := httptest.NewRecorder()
	secured.ServeHTTP(wrongScopeRecorder, wrongScope)
	if wrongScopeRecorder.Code != http.StatusForbidden {
		t.Fatalf("wrong service scope must fail: status=%d body=%s", wrongScopeRecorder.Code, wrongScopeRecorder.Body.String())
	}
}

func contentSecuredHandler(t *testing.T) http.Handler {
	t.Helper()
	verifier, err := rtauth.NewHS256Verifier(reportAccessTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	return rtauth.Middleware(rtauth.MiddlewareConfig{AccessTokenVerifier: verifier})(
		rtauth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("content"))(testHandler),
	)
}

func mediaReferenceServiceToken(t *testing.T, scopes []string) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(reportAccessTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "service:circle-service", Scopes: scopes, Roles: []string{"service"},
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}
