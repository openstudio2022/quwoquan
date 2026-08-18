// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-003.t2
package http_test

// 命令结果的布尔字段在 wire 上必须始终出现。`omitempty` 会让 `false` 整个消失，
// 而端侧 codegen 对必填 bool 生成的是 fail-closed 校验，键一旦缺失就是一次线上
// 解码失败。断言只能落在原始 JSON 上：解码进 Go 结构体后，缺键与 false 无从区分。
//
// 空列表同理，而且它有三种落法：`[]`、`null`、键消失。只有第一种是契约声明的
// 非可空列表。`json.Unmarshal` 对这三种输入都会给出 Go 侧的空切片，所以这里同样
// 只看原始 JSON——静态门禁只能证明 wire 边界没有 `omitempty`，nil 切片会不会被
// 序列化成 `null` 得看运行时。

import (
	"encoding/json"
	"net/http"
	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"strconv"
	"testing"

	commenthttp "quwoquan_service/services/content-service/internal/content/comment/adapters/inbound/http"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commenttestsupport "quwoquan_service/services/content-service/internal/content/comment/infrastructure/testsupport"
	reactionhttp "quwoquan_service/services/content-service/internal/content/content_reaction/adapters/inbound/http"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func newCommentWireHandler(t *testing.T, postID string) http.Handler {
	t.Helper()
	commentStore := commenttestsupport.NewStore()
	commentStore.SeedPost(postID, "post-owner")
	reactionStore := testsupport.NewReactionStore()
	commentService := commentapp.BindFacades(commentapp.NewCommentService(commentapp.BindDataPorts(
		commentStore,
		commentStore,
		reactionStore,
		commentStore,
		commentStore,
	)))
	reactionService := reactionapp.BindFacades(reactionapp.NewService(reactionapp.BindDataPorts(reactionStore, reactionStore)))
	return NewContentHandler(
		nil,
		nil,
		nil,
		commenthttp.NewHandler(commentService),
		reactionhttp.NewHandler(reactionService),
		nil,
		nil,
	).Routes()
}

func TestCommandResultKeepsFalseBooleanOnWire(t *testing.T) {
	t.Parallel()
	handler := newCommentWireHandler(t, "post-false-bool")

	created := performCommentRequest(t, handler, http.MethodPost,
		"/content/posts/post-false-bool/comments",
		map[string]any{"content": "first write", "mentions": []any{}},
		"false-bool-create", "comment-author")
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	assertWireBool(t, created.Body.Bytes(), "replayed", false)

	var createResult commentapp.CommentCommandResult
	if err := json.Unmarshal(created.Body.Bytes(), &createResult); err != nil {
		t.Fatal(err)
	}

	reacted := performCommentRequest(t, handler, http.MethodPost,
		"/content/comments/"+createResult.ID+"/reaction",
		map[string]any{"reaction": "dislike"},
		"false-bool-react", "comment-viewer")
	if reacted.Code != http.StatusOK {
		t.Fatalf("react status=%d body=%s", reacted.Code, reacted.Body.String())
	}
	assertWireBool(t, reacted.Body.Bytes(), "replayed", false)
}

func TestEmptyListsStayEmptyArraysOnWire(t *testing.T) {
	t.Parallel()
	handler := newCommentWireHandler(t, "post-empty-lists")

	empty := performCommentRequest(t, handler, http.MethodGet,
		"/content/posts/post-empty-lists/comments", nil, "", "comment-viewer")
	if empty.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", empty.Code, empty.Body.String())
	}
	assertWireEmptyArray(t, empty.Body.Bytes(), "items")

	created := performCommentRequest(t, handler, http.MethodPost,
		"/content/posts/post-empty-lists/comments",
		map[string]any{"content": "no attachments", "mentions": []any{}},
		"empty-lists-create", "comment-author")
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}

	listed := performCommentRequest(t, handler, http.MethodGet,
		"/content/posts/post-empty-lists/comments", nil, "", "comment-viewer")
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	// 一条无附件、无提及、无回复的评论：契约上这四个列表都是非可空的空列表。
	for _, field := range []string{
		"attachmentMediaIds",
		"attachments",
		"mentions",
		"replyPreview",
	} {
		assertWireEmptyArray(t, listed.Body.Bytes(), "items", "0", field)
	}
}

// wireValueAt 按路径下钻原始 JSON。全程用 `json.RawMessage`，因为一旦解到具体类型，
// `null`、`[]` 与缺键就已经被抹平成同一个空切片了。纯数字路径段按数组下标解释。
func wireValueAt(t *testing.T, body []byte, path ...string) json.RawMessage {
	t.Helper()
	current := json.RawMessage(body)
	for depth, key := range path {
		if index, err := strconv.Atoi(key); err == nil {
			var items []json.RawMessage
			if err := json.Unmarshal(current, &items); err != nil {
				t.Fatalf("%v 处不是数组: %v (%s)", path[:depth+1], err, current)
			}
			if index >= len(items) {
				t.Fatalf("%v 越界: 数组长度 %d", path[:depth+1], len(items))
			}
			current = items[index]
			continue
		}
		var object map[string]json.RawMessage
		if err := json.Unmarshal(current, &object); err != nil {
			t.Fatalf("%v 处不是对象: %v (%s)", path[:depth+1], err, current)
		}
		next, present := object[key]
		if !present {
			t.Fatalf("%v 键缺失: %s", path[:depth+1], current)
		}
		current = next
	}
	return current
}

func assertWireEmptyArray(t *testing.T, body []byte, path ...string) {
	t.Helper()
	raw := string(wireValueAt(t, body, path...))
	if raw != "[]" {
		t.Fatalf("%v = %s，非可空列表在 wire 上必须是 []，不能是 null 或缺键", path, raw)
	}
}

func assertWireBool(t *testing.T, body []byte, key string, want bool) {
	t.Helper()
	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal %s: %v", body, err)
	}
	raw, present := decoded[key]
	if !present {
		t.Fatalf("%q missing from response body %s", key, body)
	}
	got, ok := raw.(bool)
	if !ok {
		t.Fatalf("%q is %T, want bool: %s", key, raw, body)
	}
	if got != want {
		t.Fatalf("%q = %v, want %v", key, got, want)
	}
}
