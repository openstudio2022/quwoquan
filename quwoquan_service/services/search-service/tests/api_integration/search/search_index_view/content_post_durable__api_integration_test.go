package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"os"
	msg "quwoquan_service/runtime/messaging"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	persistence "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/contentpost"
	"quwoquan_service/services/search-service/tests/support"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentPostRealDurableProjection(t *testing.T) {
	export := os.Getenv("QWQ_SEARCH_OUTBOX_EXPORT")
	if export == "" {
		t.Fatal("real Content command outbox export required")
	}
	raw, err := os.ReadFile(export)
	if err != nil {
		t.Fatal(err)
	}
	var events []map[string]any
	if err = json.Unmarshal(raw, &events); err != nil || len(events) < 2 {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(t.Context(), 150*time.Second)
	defer cancel()
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	client, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "ordinary_post", RequestTimeout: 10 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	projection, err := persistence.New(mongoDB, es.NewIndexer(client, client.WriteIndexName()))
	if err != nil {
		t.Fatal(err)
	}
	if err = projection.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	handler, err := app.NewContentPostHandler(projection)
	if err != nil {
		t.Fatal(err)
	}
	transport, err := msg.NewRedisMessageTransport(realRedisClient, realRedisClient)
	if err != nil {
		t.Fatal(err)
	}
	consumer, err := app.NewContentPostLifecycleConsumer(transport, handler, "ordinary-search-test", "one")
	if err != nil {
		t.Fatal(err)
	}
	delivery := func(event map[string]any) msg.StreamDelivery {
		f := []msg.DurableField{}
		for k, v := range event {
			f = append(f, msg.DurableField{Name: k, Value: fmt.Sprint(v)})
		}
		return msg.StreamDelivery{Stream: "events.content.post_lifecycle", ID: "direct", Fields: f}
	}
	appendEvent := func(event map[string]any) {
		t.Helper()
		d := delivery(event)
		if _, err := transport.AppendDurable(ctx, msg.DurableMessage{Stream: d.Stream, Fields: d.Fields}); err != nil {
			t.Fatal(err)
		}
	}
	visible := func(want int) {
		t.Helper()
		deadline := time.Now().Add(10 * time.Second)
		for {
			rows, err := es.NewBackend(client, client.IndexName()).Recall(ctx, rt.RetrievePlan{Limit: 10})
			if err == nil && len(rows) == want {
				return
			}
			if time.Now().After(deadline) {
				t.Fatal("query visibility", len(rows), want, err)
			}
			time.Sleep(100 * time.Millisecond)
		}
	}
	// 真实Mongo校验器注入inbox提交故障：Provider已写，checkpoint必须回滚，事件不ACK。
	if err = mongoDB.RunCommand(ctx, bson.D{{Key: "collMod", Value: persistence.InboxCollection}, {Key: "validator", Value: bson.M{"eventDigest": bson.M{"$eq": "reject-all-test"}}}}).Err(); err != nil {
		t.Fatal(err)
	}
	appendEvent(events[0])
	if n, e := consumer.ProcessOnce(ctx); e == nil || n != 0 {
		t.Fatal("Mongo failure acknowledged", n, e)
	}
	visible(1)
	failed, _, e := transport.ReclaimDurable(ctx, "events.content.post_lifecycle", "ordinary-search-test", "probe", 0, "0-0", 50)
	if e != nil || len(failed) != 1 {
		t.Fatal("lost pending", len(failed), e)
	}
	if n, e := mongoDB.Collection(persistence.CheckpointCollection).CountDocuments(ctx, bson.M{}); e != nil || n != 0 {
		t.Fatal("checkpoint advanced on failure", n, e)
	}
	if err = mongoDB.RunCommand(ctx, bson.D{{Key: "collMod", Value: persistence.InboxCollection}, {Key: "validator", Value: bson.M{}}}).Err(); err != nil {
		t.Fatal(err)
	}
	if err = handler.ApplyContentPostDelivery(ctx, failed[0]); err != nil {
		t.Fatal("Provider-success Mongo-failure replay", err)
	}
	if err = transport.AckDurable(ctx, failed[0].Stream, "ordinary-search-test", failed[0].ID); err != nil {
		t.Fatal(err)
	}
	visible(1)
	appendEvent(events[0])
	if n, e := consumer.ProcessOnce(ctx); e != nil || n != 1 {
		t.Fatal("replay", n, e)
	}
	bad := map[string]any{}
	for k, v := range events[0] {
		bad[k] = v
	}
	var p map[string]any
	_ = json.Unmarshal([]byte(bad["payload"].(string)), &p)
	p["title"] = "tampered"
	b, _ := json.Marshal(p)
	bad["payload"] = string(b)
	if err = handler.ApplyContentPostDelivery(ctx, delivery(bad)); !errors.Is(err, app.ErrContentPostConflict) {
		t.Fatal("event conflict", err)
	}
	bad["eventId"] = "same-version-other-id"
	if err = handler.ApplyContentPostDelivery(ctx, delivery(bad)); err == nil {
		t.Fatal("same version divergent payload accepted")
	}
	for i := 1; i < len(events)-1; i++ {
		appendEvent(events[i])
		if n, e := consumer.ProcessOnce(ctx); e != nil || n != 1 {
			t.Fatal("real update", n, e)
		}
		want := 0
		if i == 2 {
			want = 1
		}
		visible(want)
	}
	appendEvent(events[len(events)-1])
	if n, e := consumer.ProcessOnce(ctx); e != nil || n != 1 {
		t.Fatal("delete", n, e)
	}
	visible(0)
	// 旧upsert不能复活；不同eventId模拟乱序递送，仍到达真实版本sink。
	stale := map[string]any{}
	for k, v := range events[0] {
		stale[k] = v
	}
	stale["eventId"] = "late-old-upsert"
	if err = handler.ApplyContentPostDelivery(ctx, delivery(stale)); err != nil {
		t.Fatal(err)
	}
	visible(0)
	count, err := mongoDB.Collection(persistence.InboxCollection).CountDocuments(ctx, bson.M{})
	if err != nil || count != int64(len(events)+1) {
		t.Fatal("inbox", count, err)
	}
	// 未知payload是pending而非ACK/成功inbox。
	bad["eventType"] = "UnknownPostEvent"
	appendEvent(bad)
	if n, e := consumer.ProcessOnce(ctx); e == nil || n != 0 {
		t.Fatal("unknown acknowledged", n, e)
	}
	pending, _, err := transport.ReclaimDurable(ctx, "events.content.post_lifecycle", "ordinary-search-test", "two", 0, "0-0", 50)
	if err != nil || len(pending) != 1 {
		t.Fatal("failed event not pending", len(pending), err)
	}
}
