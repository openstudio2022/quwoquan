// 历史分页与增量同步在乱序写入下的排序/去重/无缺号契约：
// 持久层文档以与 seq 无关的顺序写入后，keyset 分页跨页合并与 sync 增量
// 均按 seq 有序、无重复、无缺号。
//
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-paging-and-ordering/spec.md#gwt-003.t2
package api_integration

import (
	"context"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestPagingAndSyncStayOrderedWithoutDuplicatesUnderDisorderedWrites(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"disorder paging"}`)
	convID := conv["id"].(string)

	// 乱序注入：写入顺序与 seq 顺序无关（模拟并发提交的持久分布）。
	base := time.Date(2026, 8, 13, 10, 0, 0, 0, time.UTC)
	insertOrder := []int64{5, 2, 8, 1, 9, 3, 7, 4, 6, 10}
	collection := requireMongoDB(t).Collection("messages")
	for _, seq := range insertOrder {
		if _, err := collection.InsertOne(context.Background(), bson.M{
			"_id":            fmt.Sprintf("disorder-msg-%d", seq),
			"conversationId": convID,
			"seq":            seq,
			"clientMsgId":    fmt.Sprintf("disorder-client-%d", seq),
			"senderId":       "user_test_001",
			"type":           "text",
			"content":        fmt.Sprintf("乱序消息 %d", seq),
			"status":         "sent",
			"timestamp":      base.Add(time.Duration(seq) * time.Second),
			"version":        int64(1),
		}); err != nil {
			t.Fatalf("insert disordered message seq=%d: %v", seq, err)
		}
	}

	collectSeqs := func(items []any) []int64 {
		seqs := make([]int64, 0, len(items))
		for _, raw := range items {
			item := raw.(map[string]any)
			seqs = append(seqs, int64(item["seq"].(float64)))
		}
		return seqs
	}
	assertOrderedNoDuplicates := func(scenario string, seqs []int64, want []int64) {
		t.Helper()
		if len(seqs) != len(want) {
			t.Fatalf("%s length = %d want %d (%v)", scenario, len(seqs), len(want), seqs)
		}
		for index, seq := range seqs {
			if seq != want[index] {
				t.Fatalf("%s out of order at %d: got %v want %v", scenario, index, seqs, want)
			}
		}
	}

	// keyset 分页两页合并：跨页边界无重复、无缺号，按 seq 递减各自有序。
	statusCode, firstPage := doGet(
		t,
		"/chat/conversations/"+convID+"/messages?limit=4",
		"user_test_001",
	)
	if statusCode != 200 {
		t.Fatalf("first page status = %d body=%#v", statusCode, firstPage)
	}
	firstSeqs := collectSeqs(firstPage["items"].([]any))
	assertOrderedNoDuplicates("first page", firstSeqs, []int64{10, 9, 8, 7})

	statusCode, secondPage := doGet(
		t,
		fmt.Sprintf("/chat/conversations/%s/messages?limit=4&beforeSeq=%d", convID, firstSeqs[len(firstSeqs)-1]),
		"user_test_001",
	)
	if statusCode != 200 {
		t.Fatalf("second page status = %d body=%#v", statusCode, secondPage)
	}
	secondSeqs := collectSeqs(secondPage["items"].([]any))
	assertOrderedNoDuplicates("second page", secondSeqs, []int64{6, 5, 4, 3})

	// sync 增量：lastSeq 中间水位起按 seq 递增有序补齐，无重复无缺号。
	syncBody := doPost(
		t,
		"/chat/conversations/"+convID+"/sync",
		`{"lastSeq":4,"limit":50}`,
		"user_test_001",
		200,
	)
	syncSeqs := collectSeqs(syncBody["messages"].([]any))
	assertOrderedNoDuplicates("sync tail", syncSeqs, []int64{5, 6, 7, 8, 9, 10})
}
