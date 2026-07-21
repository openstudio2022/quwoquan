package application

import (
	"errors"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestChatCommercialMetricsUseOnlyBoundedLabels(t *testing.T) {
	if got := chatMentionScope([]string{"member-opaque-id"}); got != "members" {
		t.Fatalf("member mention scope = %q, want members", got)
	}
	if got := chatMentionScope([]string{"__all__", "member-opaque-id"}); got != "all" {
		t.Fatalf("all mention scope = %q, want all", got)
	}
	if got := chatMentionScope(nil); got != "" {
		t.Fatalf("empty mention scope = %q, want empty", got)
	}

	mentionSucceeded := chatMentionCommandTotal.WithLabelValues("succeeded", "members")
	beforeMention := testutil.ToFloat64(mentionSucceeded)
	recordChatMentionCommand([]string{"member-opaque-id"}, nil)
	if got := testutil.ToFloat64(mentionSucceeded); got != beforeMention+1 {
		t.Fatalf("mention counter = %v, want %v", got, beforeMention+1)
	}

	watermarkFailed := chatReadWatermarkCommandTotal.WithLabelValues("failed")
	beforeWatermark := testutil.ToFloat64(watermarkFailed)
	recordChatReadWatermarkCommand(errors.New("write failed"))
	if got := testutil.ToFloat64(watermarkFailed); got != beforeWatermark+1 {
		t.Fatalf("watermark failure counter = %v, want %v", got, beforeWatermark+1)
	}

	observeChatInboxProjectionEventLag(time.Now().UTC().Add(-time.Second))
	if count := testutil.CollectAndCount(chatInboxProjectionEventLagSeconds); count != 1 {
		t.Fatalf("projection lag collector count = %d, want 1", count)
	}
}
