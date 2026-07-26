// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001

package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	contentgenerated "quwoquan_service/services/content-service/generated/media/media_upload_session"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
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
	assertUploadPacketHidesStorageAuthority(t, initialized)

	owned := performMediaQuery(t, "/content/media/uploads/"+sessionID, owner, http.StatusOK)
	if owned["sessionId"] != sessionID || owned["status"] != "pending" {
		t.Fatalf("owner-scoped session projection drift: %#v", owned)
	}
	assertUploadPacketHidesStorageAuthority(t, owned)
	performMediaQuery(t, "/content/media/uploads/"+sessionID, "media-session-other", http.StatusNotFound)

	aborted := performMediaCommand(t, http.MethodPost, "/content/media/uploads/"+sessionID+":abort", "", owner, "media-session-abort")
	if aborted["status"] != "aborted" || aborted["replayed"] != false {
		t.Fatalf("unexpected abort result: %#v", aborted)
	}
	assertUploadPacketHidesStorageAuthority(t, aborted)
	replayed := performMediaCommand(t, http.MethodPost, "/content/media/uploads/"+sessionID+":abort", "", owner, "media-session-abort")
	if replayed["status"] != "aborted" || replayed["replayed"] != true {
		t.Fatalf("abort replay must be stable: %#v", replayed)
	}
	assertUploadPacketHidesStorageAuthority(t, replayed)
}

func TestOwnerDiscardMediaAssetIsIdempotentAndRejectsLiveReference(t *testing.T) {
	owner := "media-discard-owner"
	discardableID := completeMediaForHTTPPacket(
		t,
		owner,
		"image",
		"image/jpeg",
		"cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd",
		"owner_only",
	)
	first := performMediaCommand(
		t,
		http.MethodDelete,
		"/content/media/"+discardableID,
		"",
		owner,
		"media-discard-command",
	)
	if first["mediaId"] != discardableID ||
		first["status"] != "deleted" ||
		first["replayed"] != false {
		t.Fatalf("unexpected media discard result: %#v", first)
	}
	replayed := performMediaCommand(
		t,
		http.MethodDelete,
		"/content/media/"+discardableID,
		"",
		owner,
		"media-discard-command",
	)
	if replayed["status"] != "deleted" || replayed["replayed"] != true {
		t.Fatalf("media discard receipt did not replay: %#v", replayed)
	}
	performMediaQuery(t, "/content/media/"+discardableID, owner, http.StatusNotFound)

	referencedID := completeMediaForHTTPPacket(
		t,
		owner,
		"image",
		"image/jpeg",
		"dededededededededededededededededededededededededededededededede",
		"owner_only",
	)
	if _, err := mongoDB.Collection("posts").InsertOne(
		context.Background(),
		bson.M{
			"_id":           "post-media-discard-reference",
			"authorId":      owner,
			"status":        "pending_review",
			"mediaAssetIds": bson.A{referencedID},
		},
	); err != nil {
		t.Fatalf("seed live Post media reference: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodDelete,
		"/content/media/"+referencedID,
		nil,
	)
	request.Header.Set("X-Client-User-Id", owner)
	request.Header.Set("X-Client-Sub-Account-Id", owner)
	request.Header.Set("Idempotency-Key", "media-discard-in-use")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusConflict ||
		!strings.Contains(recorder.Body.String(), "CONTENT.USER.media_in_use") {
		t.Fatalf(
			"referenced media discard status=%d body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
}

func TestPostBindAndMediaDiscardFenceAllowsOnlyOneCommit(t *testing.T) {
	owner := identity.AnonymousFallbackSubAccountID
	mediaID := createReadyPublicationMediaAsset(t, owner, "image")
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	type response struct {
		code int
		body string
	}
	var (
		publish response
		discard response
		group   sync.WaitGroup
		start   = make(chan struct{})
	)
	group.Add(2)
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/posts:publish",
			strings.NewReader(fmt.Sprintf(
				`{"publishIntentId":"media-fence-publish-%s","localDraftId":"media-fence-draft-%s","contentType":"image","body":"并发引用围栏","visibility":"public","mediaAssetIds":["%s"],"mediaItems":[{"kind":"image","mediaId":"%s"}]}`,
				suffix,
				suffix,
				mediaID,
				mediaID,
			)),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-fence-publish-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		publish = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodDelete,
			"/content/media/"+mediaID,
			nil,
		)
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-fence-discard-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		discard = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	close(start)
	group.Wait()

	publishSucceeded :=
		publish.code == http.StatusOK || publish.code == http.StatusAccepted
	discardSucceeded := discard.code == http.StatusOK
	if publishSucceeded && discardSucceeded {
		t.Fatalf(
			"Post binding and discard both committed: publish=%s discard=%s",
			publish.body,
			discard.body,
		)
	}
	if !publishSucceeded && !discardSucceeded {
		t.Fatalf(
			"neither competing transition committed: publish=%d %s discard=%d %s",
			publish.code,
			publish.body,
			discard.code,
			discard.body,
		)
	}
	var media struct {
		Status string `bson:"processingStatus"`
	}
	if err := mongoDB.Collection("media_assets").FindOne(
		context.Background(),
		bson.M{"_id": mediaID},
	).Decode(&media); err != nil {
		t.Fatalf("read media after reference race: %v", err)
	}
	postReferences, err := mongoDB.Collection("posts").CountDocuments(
		context.Background(),
		bson.M{
			"status":        bson.M{"$ne": "deleted"},
			"mediaAssetIds": mediaID,
		},
	)
	if err != nil {
		t.Fatalf("count Post references after race: %v", err)
	}
	if (media.Status == "deleted") == (postReferences > 0) {
		t.Fatalf(
			"reference fence invariant failed: media=%s postReferences=%d",
			media.Status,
			postReferences,
		)
	}
}

func TestCommentAttachmentAndMediaDiscardFenceAllowsOnlyOneCommit(t *testing.T) {
	owner := "media-comment-fence-owner"
	postID := createCommentTestPost(t, "media-comment-fence-post-owner")
	mediaID := createReadyPublicationMediaAsset(t, owner, "image")
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	type response struct {
		code int
		body string
	}
	var (
		comment response
		discard response
		group   sync.WaitGroup
		start   = make(chan struct{})
	)
	group.Add(2)
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/posts/"+postID+"/comments",
			strings.NewReader(fmt.Sprintf(
				`{"content":"并发附件围栏","attachmentMediaIds":["%s"],"mentions":[]}`,
				mediaID,
			)),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-comment-fence-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		comment = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodDelete,
			"/content/media/"+mediaID,
			nil,
		)
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-comment-discard-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		discard = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	close(start)
	group.Wait()

	commentSucceeded := comment.code == http.StatusCreated
	discardSucceeded := discard.code == http.StatusOK
	if commentSucceeded == discardSucceeded {
		t.Fatalf(
			"comment attachment/discard race has invalid winners: comment=%d %s discard=%d %s",
			comment.code,
			comment.body,
			discard.code,
			discard.body,
		)
	}
	var media struct {
		Status string `bson:"processingStatus"`
	}
	if err := mongoDB.Collection("media_assets").FindOne(
		context.Background(),
		bson.M{"_id": mediaID},
	).Decode(&media); err != nil {
		t.Fatalf("read media after Comment reference race: %v", err)
	}
	commentReferences, err := mongoDB.Collection("comments").CountDocuments(
		context.Background(),
		bson.M{
			"status":             bson.M{"$nin": bson.A{"deleted", "tombstoned"}},
			"attachmentMediaIds": mediaID,
		},
	)
	if err != nil {
		t.Fatalf("count Comment references after race: %v", err)
	}
	if (media.Status == "deleted") == (commentReferences > 0) {
		t.Fatalf(
			"Comment reference fence invariant failed: media=%s references=%d",
			media.Status,
			commentReferences,
		)
	}
}

func TestManualCoverAndMediaDiscardFenceAllowsOnlyOneCommit(t *testing.T) {
	owner := identity.AnonymousFallbackSubAccountID
	videoID := createReadyPublicationMediaAsset(t, owner, "video")
	coverID := createReadyPublicationMediaAsset(t, owner, "image")
	suffix := fmt.Sprintf("%d", time.Now().UnixNano())
	type response struct {
		code int
		body string
	}
	var (
		cover   response
		discard response
		group   sync.WaitGroup
		start   = make(chan struct{})
	)
	group.Add(2)
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodPost,
			"/content/media/"+videoID+"/cover:manual",
			strings.NewReader(fmt.Sprintf(
				`{"coverAssetId":"%s"}`,
				coverID,
			)),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-cover-fence-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		cover = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	go func() {
		defer group.Done()
		<-start
		request := httptest.NewRequest(
			http.MethodDelete,
			"/content/media/"+coverID,
			nil,
		)
		request.Header.Set("X-Client-User-Id", owner)
		request.Header.Set("X-Client-Sub-Account-Id", owner)
		request.Header.Set("Idempotency-Key", "media-cover-discard-"+suffix)
		recorder := httptest.NewRecorder()
		testHandler.ServeHTTP(recorder, request)
		discard = response{code: recorder.Code, body: recorder.Body.String()}
	}()
	close(start)
	group.Wait()

	coverSucceeded := cover.code == http.StatusOK
	discardSucceeded := discard.code == http.StatusOK
	if coverSucceeded == discardSucceeded {
		t.Fatalf(
			"manual-cover/discard race has invalid winners: cover=%d %s discard=%d %s",
			cover.code,
			cover.body,
			discard.code,
			discard.body,
		)
	}
	var coverAsset struct {
		Status string `bson:"processingStatus"`
	}
	if err := mongoDB.Collection("media_assets").FindOne(
		context.Background(),
		bson.M{"_id": coverID},
	).Decode(&coverAsset); err != nil {
		t.Fatalf("read cover after reference race: %v", err)
	}
	manualCoverReferences, err := mongoDB.Collection("media_assets").CountDocuments(
		context.Background(),
		bson.M{
			"processingStatus":   bson.M{"$ne": "deleted"},
			"manualCoverAssetId": coverID,
		},
	)
	if err != nil {
		t.Fatalf("count manual-cover references after race: %v", err)
	}
	if (coverAsset.Status == "deleted") == (manualCoverReferences > 0) {
		t.Fatalf(
			"manual-cover reference fence invariant failed: media=%s references=%d",
			coverAsset.Status,
			manualCoverReferences,
		)
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
	assertUploadPacketHidesStorageAuthority(t, completed)

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
	assertUploadPacketHidesStorageAuthority(t, recovered)
	replayed := performMediaCommand(
		t,
		http.MethodPost,
		"/content/media/uploads/"+sessionID+":complete",
		`{"accessPolicy":"owner_only"}`,
		owner,
		"media-session-completion-recovery-complete",
	)
	if replayed["assetId"] != assetID || replayed["replayed"] != true {
		t.Fatalf(
			"complete replay must return the original MediaAsset: first=%#v replay=%#v",
			completed,
			replayed,
		)
	}
	assertUploadPacketHidesStorageAuthority(t, replayed)
	count, err := mongoDB.Collection("media_assets").CountDocuments(
		context.Background(),
		bson.M{"_id": assetID, "sourceSessionId": sessionID},
	)
	if err != nil {
		t.Fatalf("count completed MediaAsset: %v", err)
	}
	if count != 1 {
		t.Fatalf(
			"complete replay created %d assets for session %s; want exactly one",
			count,
			sessionID,
		)
	}
}

func assertUploadPacketHidesStorageAuthority(
	t *testing.T,
	packet map[string]any,
) {
	t.Helper()
	for _, forbidden := range []string{"objectKey", "cdnUrl", "presignUrl"} {
		if _, exposed := packet[forbidden]; exposed {
			t.Fatalf(
				"MediaUploadSession packet exposed internal %s: %#v",
				forbidden,
				packet,
			)
		}
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
	beforeAuto := performMediaQuery(
		t,
		"/internal/content/media/"+videoAsset,
		owner,
		http.StatusOK,
	)
	auto := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:auto", "", owner, "media-video-cover-auto")
	if auto["mediaId"] != videoAsset || auto["coverStrategy"] != "first_frame" {
		t.Fatalf("auto cover result drift: %#v", auto)
	}
	autoReplay := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:auto", "", owner, "media-video-cover-auto")
	afterAuto := performMediaQuery(
		t,
		"/internal/content/media/"+videoAsset,
		owner,
		http.StatusOK,
	)
	if autoReplay["coverStrategy"] != "first_frame" ||
		afterAuto["version"] != beforeAuto["version"] {
		t.Fatalf(
			"auto cover no-op receipt changed aggregate: before=%#v replay=%#v after=%#v",
			beforeAuto,
			autoReplay,
			afterAuto,
		)
	}
	manual := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:manual",
		`{"coverFrameTimeMs":1250}`, owner, "media-video-cover-manual")
	if manual["mediaId"] != videoAsset || manual["coverStrategy"] != "manual" || manual["coverFrameTimeMs"] != float64(1250) {
		t.Fatalf("manual cover result drift: %#v", manual)
	}
	afterManual := performMediaQuery(
		t,
		"/internal/content/media/"+videoAsset,
		owner,
		http.StatusOK,
	)
	manualReplay := performMediaCommand(t, http.MethodPost, "/content/media/"+videoAsset+"/cover:manual",
		`{"coverFrameTimeMs":1250}`, owner, "media-video-cover-manual")
	afterManualReplay := performMediaQuery(
		t,
		"/internal/content/media/"+videoAsset,
		owner,
		http.StatusOK,
	)
	if manualReplay["coverStrategy"] != "manual" ||
		afterManualReplay["version"] != afterManual["version"] {
		t.Fatalf(
			"manual cover replay changed aggregate: command=%#v replay=%#v after=%#v",
			manual,
			manualReplay,
			afterManualReplay,
		)
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
