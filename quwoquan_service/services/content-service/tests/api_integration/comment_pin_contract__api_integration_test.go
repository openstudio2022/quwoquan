package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"quwoquan_service/services/content-service/internal/application/identity"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	"strings"
	"testing"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/repository"
	"quwoquan_service/runtime/testinfra"
	contenhttp "quwoquan_service/services/content-service/internal/adapters/http"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// 直写 canonical api_integration：R-TST06 剩余缺口要求真实 HTTP + Mongo
// 证据，不能再通过新增原目录测试源补 bridge。
func TestCommentPinContractApiIntegration(t *testing.T) {
	env := setupCommentPinAPIEnv(t)

	t.Run("author can pin and unpin top-level comment", func(t *testing.T) {
		env.reset(t)

		const authorID = "post_author_pin_owner"
		postID := env.createPublishedPost(t, authorID)
		_ = env.createComment(t, postID, "fan_1", "第一条评论", "")
		target := env.createComment(t, postID, "fan_2", "第二条评论", "")
		targetID := stringField(target, "_id")
		if targetID == "" {
			t.Fatal("target comment missing _id")
		}

		before := env.findCommentByID(t, postID, authorID, "latest", targetID)
		if !boolField(before, "canPin") {
			t.Fatalf("author should see canPin=true before pin: %#v", before)
		}

		pinRec := env.request(t, http.MethodPost,
			fmt.Sprintf("/v1/content/posts/%s/comments/%s/pin", postID, targetID),
			authorID,
			"",
		)
		if pinRec.Code != http.StatusOK {
			t.Fatalf("pin comment: expected 200, got %d: %s", pinRec.Code, pinRec.Body.String())
		}
		pinBody := decodeJSONMap(t, pinRec.Body.Bytes())
		pinnedComment := nestedMap(t, pinBody, "comment")
		if !boolField(pinnedComment, "isPinned") {
			t.Fatalf("pinned response must report isPinned=true: %#v", pinnedComment)
		}
		if strings.TrimSpace(stringField(pinnedComment, "pinnedAt")) == "" {
			t.Fatalf("pinned response must include pinnedAt: %#v", pinnedComment)
		}

		pinEvents := env.eventSpy.EventsOfType("CommentPinChanged")
		if len(pinEvents) != 1 {
			t.Fatalf("expected 1 CommentPinChanged event after pin, got %d", len(pinEvents))
		}
		if got := stringField(pinEvents[0].Payload, "auditAction"); got != "pin" {
			t.Fatalf("pin event auditAction mismatch: got %q", got)
		}

		afterPin := env.listComments(t, postID, authorID, "latest")
		if len(afterPin) < 2 {
			t.Fatalf("expected at least 2 comments after pin, got %d", len(afterPin))
		}
		if got := stringField(afterPin[0], "_id"); got != targetID {
			t.Fatalf("pinned comment must be sorted first, got %q want %q", got, targetID)
		}
		if !boolField(afterPin[0], "isPinned") {
			t.Fatalf("first comment must be pinned: %#v", afterPin[0])
		}
		if !boolField(afterPin[0], "canPin") {
			t.Fatalf("author should still see canPin=true on pinned top-level comment: %#v", afterPin[0])
		}

		unpinRec := env.request(t, http.MethodDelete,
			fmt.Sprintf("/v1/content/posts/%s/comments/%s/pin", postID, targetID),
			authorID,
			"",
		)
		if unpinRec.Code != http.StatusOK {
			t.Fatalf("unpin comment: expected 200, got %d: %s", unpinRec.Code, unpinRec.Body.String())
		}
		unpinBody := decodeJSONMap(t, unpinRec.Body.Bytes())
		unpinnedComment := nestedMap(t, unpinBody, "comment")
		if boolField(unpinnedComment, "isPinned") {
			t.Fatalf("unpin response must report isPinned=false: %#v", unpinnedComment)
		}
		if value, ok := unpinnedComment["pinnedAt"]; ok && strings.TrimSpace(stringValue(value)) != "" {
			t.Fatalf("unpinned response must clear pinnedAt: %#v", unpinnedComment)
		}

		pinEvents = env.eventSpy.EventsOfType("CommentPinChanged")
		if len(pinEvents) != 2 {
			t.Fatalf("expected 2 CommentPinChanged events after unpin, got %d", len(pinEvents))
		}
		if got := stringField(pinEvents[1].Payload, "auditAction"); got != "unpin" {
			t.Fatalf("unpin event auditAction mismatch: got %q", got)
		}

		afterUnpin := env.listComments(t, postID, authorID, "latest")
		for _, item := range afterUnpin {
			if boolField(item, "isPinned") {
				t.Fatalf("no comment should remain pinned after unpin: %#v", item)
			}
		}
	})

	t.Run("non-author receives structured forbidden", func(t *testing.T) {
		env.reset(t)

		const authorID = "post_author_forbidden_owner"
		postID := env.createPublishedPost(t, authorID)
		target := env.createComment(t, postID, "fan_1", "想被置顶", "")
		targetID := stringField(target, "_id")

		rec := env.request(t, http.MethodPost,
			fmt.Sprintf("/v1/content/posts/%s/comments/%s/pin", postID, targetID),
			"other_viewer",
			"",
		)
		if rec.Code != http.StatusForbidden {
			t.Fatalf("non-author pin: expected 403, got %d: %s", rec.Code, rec.Body.String())
		}
		errResp := decodeJSONMap(t, rec.Body.Bytes())
		if got := stringField(errResp, "code"); got != "CONTENT.USER.comment_pin_forbidden" {
			t.Fatalf("expected code CONTENT.USER.comment_pin_forbidden, got %q", got)
		}
		if len(env.eventSpy.EventsOfType("CommentPinChanged")) != 0 {
			t.Fatalf("forbidden pin must not publish CommentPinChanged event")
		}
	})

	t.Run("reply pin receives structured invalid target", func(t *testing.T) {
		env.reset(t)

		const authorID = "post_author_reply_owner"
		postID := env.createPublishedPost(t, authorID)
		parent := env.createComment(t, postID, "fan_parent", "一级评论", "")
		parentID := stringField(parent, "_id")
		reply := env.createComment(t, postID, "fan_reply", "二级回复", parentID)
		replyID := stringField(reply, "_id")

		rec := env.request(t, http.MethodPost,
			fmt.Sprintf("/v1/content/posts/%s/comments/%s/pin", postID, replyID),
			authorID,
			"",
		)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("pin reply: expected 400, got %d: %s", rec.Code, rec.Body.String())
		}
		errResp := decodeJSONMap(t, rec.Body.Bytes())
		if got := stringField(errResp, "code"); got != "CONTENT.USER.comment_pin_invalid_target" {
			t.Fatalf("expected code CONTENT.USER.comment_pin_invalid_target, got %q", got)
		}
		if len(env.eventSpy.EventsOfType("CommentPinChanged")) != 0 {
			t.Fatalf("invalid target pin must not publish CommentPinChanged event")
		}
	})
}

type commentPinAPIEnv struct {
	handler     http.Handler
	eventSpy    *testinfra.EventSpy
	mongoClient *mongo.Client
	mongoDB     *mongo.Database
	container   *mongomod.MongoDBContainer
}

func setupCommentPinAPIEnv(t *testing.T) *commentPinAPIEnv {
	t.Helper()
	ctx := context.Background()
	eventSpy := testinfra.NewEventSpy()

	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	var container *mongomod.MongoDBContainer
	if mongoURI == "" {
		started, err := tryRunMongoContainer(ctx)
		if err != nil {
			t.Fatalf("TEST_MONGO_URI is required or Docker testcontainer must be available for comment pin api_integration: %v", err)
		}
		container = started
		uri, err := container.ConnectionString(ctx)
		if err != nil {
			t.Fatalf("get mongo connection string: %v", err)
		}
		mongoURI = uri
	}

	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatalf("connect mongo: %v", err)
	}
	dbName := "content_comment_pin_api_integration"
	db := client.Database(dbName)

	postStore := persistence.NewMongoPostStore(db.Collection("posts"))
	commentStore := persistence.NewMongoCommentStore(db, slog.Default())
	commentReactionStore := persistence.NewMongoCommentReactionStore(db, slog.Default())
	postService := postapp.NewPostService(
		postStore,
		postapp.WithEventPublisher(eventSpy),
		postapp.WithCommentStore(commentStore),
		postapp.WithCommentReactionStore(commentReactionStore),
	)
	baseHandler := contenhttp.NewContentHandler(nil, postService, nil, nil).Routes()
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id")) == "" {
			subAccountID := identity.AnonymousFallbackSubAccountID
			if userID := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); userID != "" {
				subAccountID = userID
			}
			r.Header.Set("X-Client-Sub-Account-Id", subAccountID)
		}
		baseHandler.ServeHTTP(w, r)
	})

	env := &commentPinAPIEnv{
		handler:     handler,
		eventSpy:    eventSpy,
		mongoClient: client,
		mongoDB:     db,
		container:   container,
	}
	t.Cleanup(func() {
		if env.mongoDB != nil {
			_ = env.mongoDB.Drop(ctx)
		}
		if env.mongoClient != nil {
			_ = env.mongoClient.Disconnect(ctx)
		}
		if env.container != nil {
			_ = env.container.Terminate(ctx)
		}
	})
	return env
}

func (e *commentPinAPIEnv) reset(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	for _, coll := range []string{"posts", "comments", "comment_reactions"} {
		if _, err := e.mongoDB.Collection(coll).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatalf("reset %s: %v", coll, err)
		}
	}
	e.eventSpy.Reset()
}

func (e *commentPinAPIEnv) request(
	t *testing.T,
	method string,
	path string,
	userID string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if strings.TrimSpace(body) != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	if strings.TrimSpace(userID) != "" {
		req.Header.Set("X-Client-User-Id", userID)
	}
	rec := httptest.NewRecorder()
	e.handler.ServeHTTP(rec, req)
	return rec
}

func (e *commentPinAPIEnv) createPublishedPost(t *testing.T, authorID string) string {
	t.Helper()
	createRec := e.request(
		t,
		http.MethodPost,
		"/v1/content/posts",
		authorID,
		`{"contentType":"image","title":"Pin target","mediaUrls":["https://example.com/img.jpg"]}`,
	)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create post: expected 201, got %d: %s", createRec.Code, createRec.Body.String())
	}
	created := decodeJSONMap(t, createRec.Body.Bytes())
	postID := stringField(created, "_id")
	if postID == "" {
		postID = stringField(created, "id")
	}
	if postID == "" {
		t.Fatalf("create post response missing id: %#v", created)
	}

	publishRec := e.request(
		t,
		http.MethodPost,
		fmt.Sprintf("/v1/content/posts/%s/publish", postID),
		authorID,
		`{}`,
	)
	if publishRec.Code != http.StatusOK {
		t.Fatalf("publish post: expected 200, got %d: %s", publishRec.Code, publishRec.Body.String())
	}
	return postID
}

func (e *commentPinAPIEnv) createComment(
	t *testing.T,
	postID string,
	authorID string,
	content string,
	replyToCommentID string,
) map[string]any {
	t.Helper()
	body := map[string]any{"content": content}
	if strings.TrimSpace(replyToCommentID) != "" {
		body["replyToCommentId"] = replyToCommentID
	}
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal comment payload: %v", err)
	}
	rec := e.request(
		t,
		http.MethodPost,
		fmt.Sprintf("/v1/content/posts/%s/comments", postID),
		authorID,
		string(payload),
	)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create comment: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	resp := decodeJSONMap(t, rec.Body.Bytes())
	return nestedMap(t, resp, "comment")
}

func (e *commentPinAPIEnv) listComments(
	t *testing.T,
	postID string,
	viewerID string,
	sort string,
) []map[string]any {
	t.Helper()
	path := fmt.Sprintf("/v1/content/posts/%s/comments?limit=20", postID)
	if strings.TrimSpace(sort) != "" {
		path += "&sort=" + sort
	}
	rec := e.request(t, http.MethodGet, path, viewerID, "")
	if rec.Code != http.StatusOK {
		t.Fatalf("list comments: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	resp := decodeJSONMap(t, rec.Body.Bytes())
	rawItems, ok := resp["items"].([]any)
	if !ok {
		t.Fatalf("list comments response missing items: %#v", resp)
	}
	items := make([]map[string]any, 0, len(rawItems))
	for _, raw := range rawItems {
		item, ok := raw.(map[string]any)
		if !ok {
			t.Fatalf("unexpected comment item type %T in %#v", raw, resp)
		}
		items = append(items, item)
	}
	return items
}

func (e *commentPinAPIEnv) findCommentByID(
	t *testing.T,
	postID string,
	viewerID string,
	sort string,
	commentID string,
) map[string]any {
	t.Helper()
	items := e.listComments(t, postID, viewerID, sort)
	for _, item := range items {
		if stringField(item, "_id") == commentID {
			return item
		}
	}
	t.Fatalf("comment %s not found in list response", commentID)
	return nil
}

func decodeJSONMap(t *testing.T, payload []byte) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(payload, &body); err != nil {
		t.Fatalf("decode json response: %v", err)
	}
	return body
}

func nestedMap(t *testing.T, body map[string]any, key string) map[string]any {
	t.Helper()
	value, ok := body[key].(map[string]any)
	if !ok {
		t.Fatalf("response missing object %q: %#v", key, body)
	}
	return value
}

func stringField(body map[string]any, key string) string {
	return stringValue(body[key])
}

func stringValue(value any) string {
	if s, ok := value.(string); ok {
		return s
	}
	return ""
}

func boolField(body map[string]any, key string) bool {
	value, ok := body[key]
	if !ok {
		return false
	}
	switch vv := value.(type) {
	case bool:
		return vv
	case string:
		return strings.EqualFold(strings.TrimSpace(vv), "true")
	default:
		return false
	}
}

var _ repository.EventPublisher = (*testinfra.EventSpy)(nil)
