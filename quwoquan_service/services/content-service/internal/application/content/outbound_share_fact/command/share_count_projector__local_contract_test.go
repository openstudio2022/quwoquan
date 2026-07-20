package command

import (
	"context"
	"testing"

	shareports "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/ports"
)

func TestShareCountProjectorRebuildsAuthoritativeCount(t *testing.T) {
	reader := &shareCountReaderForTest{count: 3}
	writer := &shareCountWriterForTest{}
	projector := NewShareCountProjector(reader, writer)
	event := shareports.OutboxEvent{
		EventID:   "share-event-1",
		EventType: outboundShareRecordedEventType,
		Payload:   []byte(`{"postId":"post-1"}`),
	}

	if err := projector.Publish(t.Context(), event); err != nil {
		t.Fatalf("project share count: %v", err)
	}
	if reader.postID != "post-1" {
		t.Fatalf("count reader postId=%q, want post-1", reader.postID)
	}
	if writer.postID != "post-1" || writer.count != 3 {
		t.Fatalf("writer projection=(%q,%d), want (post-1,3)", writer.postID, writer.count)
	}

	// relay 重放仍从权威事实集合取绝对值，不允许 $inc 双计。
	if err := projector.Publish(t.Context(), event); err != nil {
		t.Fatalf("replay share count: %v", err)
	}
	if reader.calls != 2 || writer.count != 3 || writer.calls != 2 {
		t.Fatalf(
			"replay must rebuild authoritative count: reads=%d count=%d writes=%d",
			reader.calls,
			writer.count,
			writer.calls,
		)
	}
}

func TestShareCountProjectorRejectsMissingTarget(t *testing.T) {
	projector := NewShareCountProjector(
		&shareCountReaderForTest{count: 1},
		&shareCountWriterForTest{},
	)
	err := projector.Publish(t.Context(), shareports.OutboxEvent{
		EventType: outboundShareRecordedEventType,
		Payload:   []byte(`{"postId":""}`),
	})
	if err == nil {
		t.Fatal("missing postId must fail closed")
	}
}

type shareCountReaderForTest struct {
	count  int64
	postID string
	calls  int
}

func (r *shareCountReaderForTest) CountByPost(
	_ context.Context,
	postID string,
) (int64, error) {
	r.postID = postID
	r.calls++
	return r.count, nil
}

type shareCountWriterForTest struct {
	postID string
	count  int64
	calls  int
}

func (w *shareCountWriterForTest) SetShareCount(
	_ context.Context,
	postID string,
	count int64,
) (bool, error) {
	w.postID = postID
	w.count = count
	w.calls++
	return true, nil
}
