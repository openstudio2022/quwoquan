package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMediaUploadSessionHTTPPacketPersistsOwnerScopedGetAbortAndReplay(t *testing.T) {
	owner := "media-session-owner"
	initialized := performMediaCommand(t, http.MethodPost, "/content/media/uploads:init",
		`{"mediaType":"image","contentType":"image/jpeg","fileSize":64,"expectedSha256":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}`,
		owner, "media-session-init")
	sessionID := asTestString(initialized["sessionId"])
	if sessionID == "" {
		t.Fatalf("init result has no sessionId: %#v", initialized)
	}

	owned := performMediaQuery(t, "/content/media/uploads/"+sessionID, owner, http.StatusOK)
	if owned["sessionId"] != sessionID || owned["status"] != "pending" {
		t.Fatalf("owner-scoped session projection drift: %#v", owned)
	}
	performMediaQuery(t, "/content/media/uploads/"+sessionID, "media-session-other", http.StatusNotFound)

	aborted := performMediaCommand(t, http.MethodPost, "/content/media/uploads/"+sessionID+":abort", "", owner, "media-session-abort")
	if aborted["status"] != "aborted" || aborted["replayed"] != false {
		t.Fatalf("unexpected abort result: %#v", aborted)
	}
	replayed := performMediaCommand(t, http.MethodPost, "/content/media/uploads/"+sessionID+":abort", "", owner, "media-session-abort")
	if replayed["status"] != "aborted" || replayed["replayed"] != true {
		t.Fatalf("abort replay must be stable: %#v", replayed)
	}
}

func TestMediaAssetHTTPPacketExposesOnlyPublicReadyAssetsAndOwnsVideoCover(t *testing.T) {
	owner := "media-asset-owner"
	publicAsset := completeMediaForHTTPPacket(t, owner, "image", "image/png", "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "public")
	publicView := performMediaQuery(t, "/content/media/"+publicAsset, "", http.StatusOK)
	if publicView["assetId"] != publicAsset || publicView["accessPolicy"] != "public" || publicView["status"] != "ready" {
		t.Fatalf("public MediaAsset slice drift: %#v", publicView)
	}

	videoAsset := completeMediaForHTTPPacket(t, owner, "video", "video/mp4", "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "owner_only")
	performMediaCommand(t, http.MethodPost, "/internal/content/media/"+videoAsset+":processing-result",
		`{"processingStatus":"ready"}`, owner, "media-video-processing-ready")
	auto := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:auto", "", owner, "media-video-cover-auto")
	if auto["mediaId"] != videoAsset || auto["coverStrategy"] != "first_frame" {
		t.Fatalf("auto cover result drift: %#v", auto)
	}
	manual := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:manual",
		`{"coverFrameTimeMs":1250}`, owner, "media-video-cover-manual")
	if manual["mediaId"] != videoAsset || manual["coverStrategy"] != "manual" || manual["coverFrameTimeMs"] != float64(1250) {
		t.Fatalf("manual cover result drift: %#v", manual)
	}
}

func completeMediaForHTTPPacket(t *testing.T, owner, mediaType, contentType, digest, policy string) string {
	t.Helper()
	prefix := "media-packet-" + mediaType + "-" + digest[:8]
	initialized := performMediaCommand(t, http.MethodPost, "/content/media/uploads:init",
		`{"mediaType":"`+mediaType+`","contentType":"`+contentType+`","fileSize":128,"expectedSha256":"sha256:`+digest+`"}`,
		owner, prefix+"-init")
	sessionID := asTestString(initialized["sessionId"])
	completed := performMediaCommand(t, http.MethodPost, "/content/media/uploads/"+sessionID+":complete",
		`{"accessPolicy":"`+policy+`"}`, owner, prefix+"-complete")
	assetID := asTestString(completed["assetId"])
	if assetID == "" {
		t.Fatalf("completed media has no assetId: %#v", completed)
	}
	return assetID
}

func performMediaCommand(t *testing.T, method, path, body, owner, idempotencyKey string) map[string]any {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", owner)
	request.Header.Set("X-Client-Sub-Account-Id", owner)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("%s %s status=%d body=%s", method, path, recorder.Code, recorder.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode %s %s: %v", method, path, err)
	}
	return result
}

func performMediaQuery(t *testing.T, path, owner string, expectedStatus int) map[string]any {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, path, nil)
	if owner != "" {
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
	}
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != expectedStatus {
		t.Fatalf("GET %s status=%d want=%d body=%s", path, recorder.Code, expectedStatus, recorder.Body.String())
	}
	if expectedStatus != http.StatusOK {
		return nil
	}
	var result map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode GET %s: %v", path, err)
	}
	return result
}
