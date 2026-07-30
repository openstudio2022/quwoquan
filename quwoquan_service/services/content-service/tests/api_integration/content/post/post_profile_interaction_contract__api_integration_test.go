package api_integration

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"
)

type profileInteractionPageBody struct {
	Items      []profileInteractionItemBody `json:"items"`
	NextCursor string                       `json:"nextCursor"`
	HasMore    bool                         `json:"hasMore"`
}

type profileInteractionItemBody struct {
	ActivityID         string     `json:"activityId"`
	ActivityType       string     `json:"activityType"`
	Direction          string     `json:"direction"`
	TargetContentID    string     `json:"targetContentId"`
	TargetAvailability string     `json:"targetAvailability"`
	PreviewUnavailable bool       `json:"previewUnavailable"`
	SeenAt             *time.Time `json:"seenAt"`
	ReadAt             *time.Time `json:"readAt"`
}

type profileReadFactAckBody struct {
	FactID   string `json:"factId"`
	Replayed bool   `json:"replayed"`
}

func TestProfileInteractionDurableSourcesMaterializeProjection(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postID := createProfileInteractionTarget(t, "profile-owner", "durable-sources")

	createProfileInteractionLike(t, postID, "profile-like-actor", "like-durable")
	createProfileInteractionComment(t, postID, "profile-comment-actor", "comment-durable")
	createProfileInteractionShare(t, postID, "profile-share-actor", "share-durable")

	for _, activityType := range []string{"like", "comment", "share"} {
		page := listProfileInteractions(
			t,
			"profile-owner",
			"profile-owner",
			"received",
			activityType,
			"",
			20,
		)
		if len(page.Items) != 1 {
			t.Fatalf("%s projection items=%d body=%+v", activityType, len(page.Items), page)
		}
		item := page.Items[0]
		if item.ActivityType != activityType ||
			item.Direction != "received" ||
			item.TargetContentID != postID {
			t.Fatalf("%s projection mismatch: %+v", activityType, item)
		}
	}

	// 每个 durable consumer 重放同一 checkpoint 后必须保持一行。
	if _, err := profileReactionRelay.Drain(t.Context(), 100); err != nil {
		t.Fatalf("replay reaction projector: %v", err)
	}
	if _, err := profileCommentRelay.Drain(t.Context(), 100); err != nil {
		t.Fatalf("replay comment projector: %v", err)
	}
	if _, err := profileShareRelay.Drain(t.Context(), 100); err != nil {
		t.Fatalf("replay share projector: %v", err)
	}
	for _, activityType := range []string{"like", "comment", "share"} {
		page := listProfileInteractions(
			t,
			"profile-owner",
			"profile-owner",
			"received",
			activityType,
			"",
			20,
		)
		if len(page.Items) != 1 {
			t.Fatalf("%s replay created duplicates: %+v", activityType, page.Items)
		}
	}
}

func TestProfileInteractionProjectionKeysetPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postID := createProfileInteractionTarget(t, "pagination-owner", "pagination")
	for index := 0; index < 5; index++ {
		createProfileInteractionLike(
			t,
			postID,
			fmt.Sprintf("pagination-actor-%d", index),
			fmt.Sprintf("pagination-like-%d", index),
		)
	}

	seen := map[string]struct{}{}
	cursor := ""
	for pageIndex := 0; ; pageIndex++ {
		page := listProfileInteractions(
			t,
			"pagination-owner",
			"pagination-owner",
			"received",
			"like",
			cursor,
			2,
		)
		for _, item := range page.Items {
			if _, exists := seen[item.ActivityID]; exists {
				t.Fatalf("duplicate activity across pages: %s", item.ActivityID)
			}
			seen[item.ActivityID] = struct{}{}
		}
		if !page.HasMore {
			if page.NextCursor != "" {
				t.Fatalf("terminal page emitted cursor %q", page.NextCursor)
			}
			break
		}
		if page.NextCursor == "" {
			t.Fatal("non-terminal page has no cursor")
		}
		cursor = page.NextCursor
		if pageIndex > 10 {
			t.Fatal("profile interaction pagination did not terminate")
		}
	}
	if len(seen) != 5 {
		t.Fatalf("pagination covered %d activities, want 5", len(seen))
	}

	request := profileInteractionListRequest(
		"pagination-owner",
		"pagination-owner",
		"received",
		"like",
		"broken-cursor",
		2,
	)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("invalid cursor status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func TestProfileInteractionDeletedTargetBecomesUnavailable(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postID := createProfileInteractionTarget(t, "deleted-owner", "deleted-target")
	createProfileInteractionLike(t, postID, "deleted-like-actor", "deleted-like")

	request := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	request.Header.Set("X-Client-User-Id", "deleted-owner")
	request.Header.Set("X-Client-Persona-Id", "deleted-owner")
	request.Header.Set("Idempotency-Key", "delete-profile-target")
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("delete target status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	page := listProfileInteractions(
		t,
		"deleted-owner",
		"deleted-owner",
		"received",
		"like",
		"",
		20,
	)
	if len(page.Items) != 1 {
		t.Fatalf("deleted target activity must remain: %+v", page.Items)
	}
	if page.Items[0].TargetAvailability != "deleted" ||
		!page.Items[0].PreviewUnavailable {
		t.Fatalf("deleted target state mismatch: %+v", page.Items[0])
	}
}

func TestProfileInteractionReadFactAppendIsIdempotent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postID := createProfileInteractionTarget(t, "read-owner", "read-idempotent")
	createProfileInteractionShare(t, postID, "read-share-actor", "read-share")
	item := listProfileInteractions(
		t,
		"read-owner",
		"read-owner",
		"received",
		"share",
		"",
		20,
	).Items[0]

	first := appendProfileReadFact(t, "read-owner", item.ActivityID, "seen", "read-seen-1")
	second := appendProfileReadFact(t, "read-owner", item.ActivityID, "seen", "read-seen-2")
	if first.FactID == "" || second.FactID != first.FactID || second.Replayed != true {
		t.Fatalf("semantic read fact dedupe mismatch first=%+v second=%+v", first, second)
	}
}

func TestProfileInteractionReadFactProjectsMonotonicState(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	postID := createProfileInteractionTarget(t, "monotonic-owner", "read-monotonic")
	createProfileInteractionShare(t, postID, "monotonic-share-actor", "monotonic-share")
	item := listProfileInteractions(
		t,
		"monotonic-owner",
		"monotonic-owner",
		"received",
		"share",
		"",
		20,
	).Items[0]

	appendProfileReadFact(t, "monotonic-owner", item.ActivityID, "read", "monotonic-read")
	afterRead := listProfileInteractions(
		t,
		"monotonic-owner",
		"monotonic-owner",
		"received",
		"share",
		"",
		20,
	).Items[0]
	if afterRead.SeenAt == nil || afterRead.ReadAt == nil {
		t.Fatalf("read must project seenAt and readAt: %+v", afterRead)
	}
	readAt := *afterRead.ReadAt

	appendProfileReadFact(t, "monotonic-owner", item.ActivityID, "seen", "monotonic-seen")
	afterSeen := listProfileInteractions(
		t,
		"monotonic-owner",
		"monotonic-owner",
		"received",
		"share",
		"",
		20,
	).Items[0]
	if afterSeen.ReadAt == nil || !afterSeen.ReadAt.Equal(readAt) {
		t.Fatalf("seen replay regressed readAt: before=%s after=%v", readAt, afterSeen.ReadAt)
	}
}

func createProfileInteractionTarget(t *testing.T, owner, suffix string) string {
	t.Helper()
	created := submitPublishedPostWithAuthor(
		t,
		owner,
		fmt.Sprintf(`{"contentType":"image","title":"profile-%s"}`, suffix),
	)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatalf("missing profile interaction post id: %+v", created)
	}
	return postID
}

func createProfileInteractionLike(t *testing.T, postID, actor, idempotencyKey string) {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
	request.Header.Set("X-Client-User-Id", actor)
	request.Header.Set("X-Client-Persona-Id", actor)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("create profile like status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func createProfileInteractionComment(t *testing.T, postID, actor, idempotencyKey string) {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/"+postID+"/comments",
		bytes.NewBufferString(`{"content":"durable profile comment"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", actor)
	request.Header.Set("X-Client-Persona-Id", actor)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create profile comment status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func createProfileInteractionShare(t *testing.T, postID, actor, idempotencyKey string) {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/"+postID+"/outbound-shares",
		bytes.NewBufferString(
			`{"channel":"system_share","destinationKind":"external_app","destination":"profile-recipient","referralId":"profile-referral","deliverySucceeded":true,"providerReceiptId":"profile-receipt","clientConfirmedAt":"2026-07-28T20:00:00Z"}`,
		),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", actor)
	request.Header.Set("X-Client-Persona-Id", actor)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusCreated {
		t.Fatalf("create profile share status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func listProfileInteractions(
	t *testing.T,
	owner string,
	viewer string,
	direction string,
	activityType string,
	cursor string,
	limit int,
) profileInteractionPageBody {
	t.Helper()
	request := profileInteractionListRequest(
		owner,
		viewer,
		direction,
		activityType,
		cursor,
		limit,
	)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("list profile interactions status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var page profileInteractionPageBody
	if err := json.Unmarshal(recorder.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode profile interaction page: %v", err)
	}
	return page
}

func profileInteractionListRequest(
	owner string,
	viewer string,
	direction string,
	activityType string,
	cursor string,
	limit int,
) *http.Request {
	query := url.Values{
		"type":  []string{activityType},
		"limit": []string{fmt.Sprintf("%d", limit)},
	}
	if cursor != "" {
		query.Set("cursor", cursor)
	}
	request := httptest.NewRequest(
		http.MethodGet,
		fmt.Sprintf(
			"/content/personas/%s/interactions/%s?%s",
			owner,
			direction,
			query.Encode(),
		),
		nil,
	)
	request.Header.Set("X-Client-User-Id", viewer)
	request.Header.Set("X-Client-Persona-Id", viewer)
	return request
}

func appendProfileReadFact(
	t *testing.T,
	owner string,
	activityID string,
	state string,
	idempotencyKey string,
) profileReadFactAckBody {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		fmt.Sprintf(
			"/content/personas/%s/interactions/%s/read-facts",
			owner,
			activityID,
		),
		bytes.NewBufferString(fmt.Sprintf(`{"state":%q}`, state)),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Client-User-Id", owner)
	request.Header.Set("X-Client-Persona-Id", owner)
	request.Header.Set("Idempotency-Key", idempotencyKey)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("append read fact status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var ack profileReadFactAckBody
	if err := json.Unmarshal(recorder.Body.Bytes(), &ack); err != nil {
		t.Fatalf("decode read fact ack: %v", err)
	}
	return ack
}
