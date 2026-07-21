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

	contentgenerated "quwoquan_service/services/content-service/internal/generated"
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

func TestCompletedMediaUploadSessionQueryRecoversAssetIdentity(t *testing.T) {
	owner := "media-session-completion-recovery-owner"
	initialized := performMediaCommand(
		t,
		http.MethodPost,
		"/content/media/uploads:init",
		`{"mediaType":"video","contentType":"video/mp4","fileSize":64,"expectedSha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}`,
		owner,
		"media-session-completion-recovery-init",
	)
	sessionID := asTestString(initialized["sessionId"])
	if sessionID == "" {
		t.Fatalf("init result has no sessionId: %#v", initialized)
	}

	completed := performMediaCommand(
		t,
		http.MethodPost,
		"/content/media/uploads/"+sessionID+":complete",
		`{"accessPolicy":"owner_only"}`,
		owner,
		"media-session-completion-recovery-complete",
	)
	assetID := asTestString(completed["assetId"])
	if assetID == "" {
		t.Fatalf("complete result has no assetId: %#v", completed)
	}

	recovered := performMediaQuery(
		t,
		"/content/media/uploads/"+sessionID,
		owner,
		http.StatusOK,
	)
	if recovered["sessionId"] != sessionID ||
		recovered["status"] != "completed" ||
		recovered["assetId"] != assetID {
		t.Fatalf(
			"completed session must retain recoverable asset identity: %#v",
			recovered,
		)
	}
}

func TestMediaUploadAdmissionRejectsUnsupportedAndOversizedPayloadsBeforePersistence(
	t *testing.T,
) {
	owner := "media-admission-rejected-owner"
	testCases := []struct {
		name           string
		body           string
		expectedStatus int
		expectedCode   string
	}{
		{
			name: "oversized_video",
			body: `{"mediaType":"video","contentType":"video/mp4","fileSize":52428801,` +
				`"expectedSha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111"}`,
			expectedStatus: http.StatusRequestEntityTooLarge,
			expectedCode:   contentgenerated.ErrMediaFileTooLarge.Error(),
		},
		{
			name: "mismatched_content_type",
			body: `{"mediaType":"video","contentType":"image/png","fileSize":1024,` +
				`"expectedSha256":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}`,
			expectedStatus: http.StatusUnsupportedMediaType,
			expectedCode:   contentgenerated.ErrMediaTypeUnsupported.Error(),
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodPost,
				"/content/media/uploads:init",
				strings.NewReader(testCase.body),
			)
			request.Header.Set("Content-Type", "application/json")
			request.Header.Set("X-Client-User-Id", owner)
			request.Header.Set("X-Client-Sub-Account-Id", owner)
			request.Header.Set("Idempotency-Key", "media-admission-"+testCase.name)
			response := httptest.NewRecorder()
			testHandler.ServeHTTP(response, request)
			assertRuntimeErrorResponse(
				t,
				response,
				testCase.expectedStatus,
				testCase.expectedCode,
			)
		})
	}
	count, err := mongoDB.Collection("media_upload_sessions").CountDocuments(
		context.Background(),
		bson.M{"ownerId": owner},
	)
	if err != nil {
		t.Fatalf("count rejected media upload sessions: %v", err)
	}
	if count != 0 {
		t.Fatalf("rejected media admission persisted %d upload sessions", count)
	}
}

func TestMediaAssetHTTPPacketExposesOnlyPublicReadyAssetsAndOwnsVideoCover(t *testing.T) {
	owner := "media-asset-owner"
	publicAsset := completeMediaForHTTPPacket(t, owner, "image", "image/png", "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "public")
	performMediaCommand(
		t,
		http.MethodPost,
		"/internal/content/media/"+publicAsset+":processing-result",
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
		}`, publicAsset, publicAsset),
		owner,
		"media-image-processing-ready",
	)
	publicView := performMediaQuery(t, "/content/media/"+publicAsset, "", http.StatusOK)
	if publicView["assetId"] != publicAsset ||
		publicView["accessPolicy"] != "public" ||
		publicView["status"] != "ready" ||
		publicView["imageDominantColor"] != "#1A2B3C" ||
		publicView["imageContentProfile"] != "alpha_graphic" ||
		publicView["imageDerivativePolicyVersion"] != float64(1) {
		t.Fatalf("public MediaAsset slice drift: %#v", publicView)
	}

	ownedView := performMediaQuery(
		t,
		"/internal/content/media/"+publicAsset,
		owner,
		http.StatusOK,
	)
	if ownedView["assetId"] != publicAsset ||
		ownedView["accessPolicy"] != "public" ||
		ownedView["status"] != "ready" {
		t.Fatalf("owner MediaAsset slice drift: %#v", ownedView)
	}
	performMediaQuery(
		t,
		"/internal/content/media/"+publicAsset,
		"other-media-asset-owner",
		http.StatusNotFound,
	)

	videoAsset := completeMediaForHTTPPacket(t, owner, "video", "video/mp4", "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "owner_only")
	performMediaCommand(t, http.MethodPost, "/internal/content/media/"+videoAsset+":processing-result",
		fmt.Sprintf(`{
			"processingStatus":"ready",
			"processorProfile":"media_canary_progressive_mp4",
			"verifiedDurationMs":125000,
			"videoWidth":540,
			"videoHeight":960,
			"videoCodec":"h264",
			"videoContainer":"mp4",
			"videoAudioCodec":"aac",
			"videoKeyframeIntervalMs":2000,
			"videoFastStart":true,
			"videoPublicSliceKey":"media/video/s/asset/%s/v2/source.mp4",
			"coverPublicSliceKey":"media/video/s/asset/%s/v2/cover.webp",
			"previewTrackVersion":1,
			"previewTrackManifestSliceKey":"media/video/s/asset/%s/v2/preview/manifest.json"
		}`, videoAsset, videoAsset, videoAsset), owner, "media-video-processing-ready")
	auto := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:auto", "", owner, "media-video-cover-auto")
	if auto["mediaId"] != videoAsset || auto["coverStrategy"] != "first_frame" {
		t.Fatalf("auto cover result drift: %#v", auto)
	}
	manual := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:manual",
		`{"coverFrameTimeMs":1250}`, owner, "media-video-cover-manual")
	if manual["mediaId"] != videoAsset || manual["coverStrategy"] != "manual" || manual["coverFrameTimeMs"] != float64(1250) {
		t.Fatalf("manual cover result drift: %#v", manual)
	}

	for _, testCase := range []struct {
		mediaType   string
		contentType string
		digest      string
	}{
		{
			mediaType:   "audio",
			contentType: "audio/mpeg",
			digest:      "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
		},
		{
			mediaType:   "file",
			contentType: "application/pdf",
			digest:      "abababababababababababababababababababababababababababababababab",
		},
	} {
		t.Run(testCase.mediaType+"_without_processor_is_ready", func(t *testing.T) {
			assetID := completeMediaForHTTPPacket(
				t,
				owner,
				testCase.mediaType,
				testCase.contentType,
				testCase.digest,
				"public",
			)
			view := performMediaQuery(t, "/content/media/"+assetID, "", http.StatusOK)
			if view["status"] != "ready" {
				t.Fatalf(
					"%s asset has no processing consumer and must be ready: %#v",
					testCase.mediaType,
					view,
				)
			}
		})
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
