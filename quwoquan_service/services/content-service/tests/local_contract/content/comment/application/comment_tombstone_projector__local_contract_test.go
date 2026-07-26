package comment_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestCommentTombstoneProjectorAppliesPostDeletedOnce(t *testing.T) {
	t.Parallel()

	writer := &commentTombstoneWriterFixture{affected: 3}
	projector := commentapp.NewCommentTombstoneProjector(writer)
	event := postports.OutboxEvent{
		EventID:   "post-event-1",
		EventType: "PostDeleted",
		Payload:   json.RawMessage(`{"postId":"post-1"}`),
	}

	if err := projector.Publish(context.Background(), event); err != nil {
		t.Fatalf("投影 PostDeleted 失败：%v", err)
	}
	if writer.calls != 1 || writer.postID != "post-1" {
		t.Fatalf("tombstone 调用 = %d/%q，期望 1/post-1", writer.calls, writer.postID)
	}

	if err := projector.Publish(
		context.Background(),
		postports.OutboxEvent{EventType: "PostUpdated"},
	); err != nil {
		t.Fatalf("非删除事实应被忽略：%v", err)
	}
	if writer.calls != 1 {
		t.Fatalf("非删除事实触发了额外写入：calls=%d", writer.calls)
	}
}

func TestCommentTombstoneProjectorRejectsInvalidFactAndPropagatesWriterFailure(
	t *testing.T,
) {
	t.Parallel()

	projector := commentapp.NewCommentTombstoneProjector(
		&commentTombstoneWriterFixture{},
	)
	for name, payload := range map[string]json.RawMessage{
		"malformed": json.RawMessage(`{`),
		"missing":   json.RawMessage(`{"postId":" "}`),
	} {
		t.Run(name, func(t *testing.T) {
			err := projector.Publish(context.Background(), postports.OutboxEvent{
				EventType: "PostDeleted",
				Payload:   payload,
			})
			if err == nil {
				t.Fatal("无效 PostDeleted 事实未被拒绝")
			}
		})
	}

	writeErr := errors.New("mongo unavailable")
	projector = commentapp.NewCommentTombstoneProjector(
		&commentTombstoneWriterFixture{err: writeErr},
	)
	err := projector.Publish(context.Background(), postports.OutboxEvent{
		EventType: "PostDeleted",
		Payload:   json.RawMessage(`{"postId":"post-2"}`),
	})
	if !errors.Is(err, writeErr) ||
		!strings.Contains(err.Error(), "tombstone comments for deleted post") {
		t.Fatalf("写入错误未按契约传播：%v", err)
	}
}

type commentTombstoneWriterFixture struct {
	affected int64
	err      error
	calls    int
	postID   string
}

func (f *commentTombstoneWriterFixture) TombstoneCommentsByPost(
	_ context.Context,
	postID string,
) (int64, error) {
	f.calls++
	f.postID = postID
	return f.affected, f.err
}
