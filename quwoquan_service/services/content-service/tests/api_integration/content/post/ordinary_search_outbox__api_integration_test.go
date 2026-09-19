package api_integration

import (
	"context"
	"encoding/json"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 导出真实owner命令持久outbox字节供独立Search owner集成消费，不跨服务internal。
func TestOrdinarySearchOwnerOutboxExport(t *testing.T) {
	target := os.Getenv("QWQ_SEARCH_OUTBOX_EXPORT")
	if target == "" {
		t.Skip("explicit disposable export path required")
	}
	created := submitPublishedPostWithAuthor(t, "search-outbox-author", `{"contentType":"article","body":"洱海骑行搜索闭环"}`)
	id := created["postId"].(string)
	for _, visibility := range []string{"private", "public"} {
		request := httptest.NewRequest(http.MethodPatch, "/content/posts/"+id+"/settings", strings.NewReader(`{"visibility":"`+visibility+`"}`))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("X-Client-User-Id", "search-outbox-author")
		request.Header.Set("Idempotency-Key", "ordinary-search-settings-"+visibility)
		result := httptest.NewRecorder()
		testHandler.ServeHTTP(result, request)
		if result.Code != 200 {
			t.Fatal("real update", result.Code, result.Body.String())
		}
	}
	request := httptest.NewRequest(http.MethodDelete, "/content/posts/"+id, nil)
	request.Header.Set("X-Client-User-Id", "search-outbox-author")
	request.Header.Set("Idempotency-Key", "ordinary-search-delete")
	result := httptest.NewRecorder()
	testHandler.ServeHTTP(result, request)
	if result.Code != 200 {
		t.Fatal(result.Code, result.Body.String())
	}
	cursor, err := mongoDB.Collection("content_outbox").Find(context.Background(), bson.M{"aggregateId": id}, options.Find().SetSort(bson.D{{Key: "aggregateVersion", Value: 1}}))
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(context.Background())
	var facts []bson.M
	if err = cursor.All(context.Background(), &facts); err != nil {
		t.Fatal(err)
	}
	rows := []map[string]any{}
	for _, f := range facts {
		raw, ok := f["payloadJson"].(bson.Binary)
		if !ok {
			t.Fatalf("outbox byte type %T", f["payloadJson"])
		}
		rows = append(rows, map[string]any{"eventId": f["_id"], "eventType": f["eventType"], "aggregateId": f["aggregateId"], "aggregateType": f["aggregateType"], "aggregateVersion": f["aggregateVersion"], "payload": string(raw.Data), "occurredAt": f["occurredAt"].(bson.DateTime).Time().UTC().Format("2006-01-02T15:04:05.999999999Z07:00")})
	}
	if len(rows) != 4 {
		t.Fatal("expected real publish/delete", len(rows))
	}
	raw, err := json.Marshal(rows)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(target, raw, 0600); err != nil {
		t.Fatal(err)
	}
}
