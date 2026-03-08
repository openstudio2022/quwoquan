package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

func BenchmarkSendMessage(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	conv := benchCreateConversation(b, `{"type":"group","title":"bench send msg","maxGroupSize":500}`)
	convId := conv["_id"].(string)

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		var seq int64
		for pb.Next() {
			n := atomic.AddInt64(&seq, 1)
			payload := fmt.Sprintf(`{"type":"text","content":"bench msg","clientMsgId":"bench-%d"}`, n)
			req := httptest.NewRequest(http.MethodPost,
				"/v1/chat/conversations/"+convId+"/messages",
				strings.NewReader(payload))
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("X-Client-User-Id", "user_bench_001")
			rec := httptest.NewRecorder()
			testHandler.ServeHTTP(rec, req)
			if rec.Code != http.StatusCreated {
				b.Errorf("expected 201, got %d: %s", rec.Code, rec.Body.String())
			}
		}
	})
}

func BenchmarkSendMessageConcurrent1000(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	conv := benchCreateConversation(b, `{"type":"group","title":"bench concurrent","maxGroupSize":500}`)
	convId := conv["_id"].(string)

	const concurrency = 100
	messagesPerWorker := 10

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var wg sync.WaitGroup
		var counter int64
		var errCount int64

		for w := 0; w < concurrency; w++ {
			wg.Add(1)
			go func(workerID int) {
				defer wg.Done()
				for m := 0; m < messagesPerWorker; m++ {
					n := atomic.AddInt64(&counter, 1)
					payload := fmt.Sprintf(`{"type":"text","content":"concurrent msg","clientMsgId":"conc-%d-%d"}`, workerID, n)
					req := httptest.NewRequest(http.MethodPost,
						"/v1/chat/conversations/"+convId+"/messages",
						strings.NewReader(payload))
					req.Header.Set("Content-Type", "application/json")
					req.Header.Set("X-Client-User-Id", fmt.Sprintf("user_bench_%03d", workerID))
					rec := httptest.NewRecorder()
					testHandler.ServeHTTP(rec, req)
					if rec.Code != http.StatusCreated {
						atomic.AddInt64(&errCount, 1)
					}
				}
			}(w)
		}
		wg.Wait()

		if errCount > 0 {
			b.Errorf("%d/%d requests failed", errCount, concurrency*messagesPerWorker)
		}
	}
}

func BenchmarkSyncMessages10K(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	conv := benchCreateConversation(b, `{"type":"group","title":"bench sync 10K","maxGroupSize":500}`)
	convId := conv["_id"].(string)

	// Seed messages (use a smaller count for benchmark setup; 10K in real env)
	const seedCount = 200
	for i := 0; i < seedCount; i++ {
		payload := fmt.Sprintf(`{"type":"text","content":"seed %d","clientMsgId":"seed-%d"}`, i, i)
		req := httptest.NewRequest(http.MethodPost,
			"/v1/chat/conversations/"+convId+"/messages",
			strings.NewReader(payload))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			b.Fatalf("seed msg %d: expected 201, got %d", i, rec.Code)
		}
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(http.MethodPost,
			"/v1/chat/conversations/"+convId+"/sync",
			strings.NewReader(`{"lastSeq":0,"limit":100}`))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			b.Errorf("sync: expected 200, got %d", rec.Code)
		}
	}
}

func BenchmarkListMessages(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	conv := benchCreateConversation(b, `{"type":"group","title":"bench list msgs","maxGroupSize":500}`)
	convId := conv["_id"].(string)

	for i := 0; i < 100; i++ {
		payload := fmt.Sprintf(`{"type":"text","content":"list bench %d","clientMsgId":"lb-%d"}`, i, i)
		req := httptest.NewRequest(http.MethodPost,
			"/v1/chat/conversations/"+convId+"/messages",
			strings.NewReader(payload))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(http.MethodGet,
			"/v1/chat/conversations/"+convId+"/messages?limit=50",
			nil)
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			b.Errorf("list: expected 200, got %d", rec.Code)
		}
	}
}

func BenchmarkAddMembers50(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	// Build a payload with 50 user IDs
	userIds := make([]string, 50)
	for i := range userIds {
		userIds[i] = fmt.Sprintf(`"user_member_%03d"`, i)
	}
	membersPayload := `{"userIds":[` + strings.Join(userIds, ",") + `]}`

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		b.StopTimer()
		conv := benchCreateConversation(b, `{"type":"group","title":"bench members","maxGroupSize":500}`)
		convId := conv["_id"].(string)
		b.StartTimer()

		req := httptest.NewRequest(http.MethodPost,
			"/v1/chat/conversations/"+convId+"/members",
			strings.NewReader(membersPayload))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			b.Errorf("add members: expected 200, got %d: %s", rec.Code, rec.Body.String())
		}
	}
}

func BenchmarkCreateConversation(b *testing.B) {
	cleanAllBench(b)
	b.Cleanup(func() { cleanAllBench(b) })

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		payload := fmt.Sprintf(`{"type":"group","title":"bench conv %d","maxGroupSize":500}`, i)
		req := httptest.NewRequest(http.MethodPost,
			"/v1/chat/conversations",
			strings.NewReader(payload))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", "user_bench_001")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusCreated {
			b.Errorf("create: expected 201, got %d", rec.Code)
		}
	}
}

// --- Bench helpers (use testing.B instead of testing.T) ---

func cleanAllBench(b *testing.B) {
	b.Helper()
	if mongoDB == nil {
		return
	}
	ctx := context.Background()
	for _, name := range collections {
		_, _ = mongoDB.Collection(name).DeleteMany(ctx, map[string]any{})
	}
	mr.FlushAll()
}

func benchCreateConversation(b *testing.B, payload string) map[string]any {
	b.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/conversations", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_bench_001")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		b.Fatalf("benchCreateConversation: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := jsonUnmarshalBytes(rec.Body.Bytes(), &result); err != nil {
		b.Fatalf("benchCreateConversation: decode: %v", err)
	}
	return result
}

func jsonUnmarshalBytes(data []byte, v any) error {
	return json.Unmarshal(data, v)
}
