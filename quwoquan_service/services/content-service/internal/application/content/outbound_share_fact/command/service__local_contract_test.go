package command

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	sharemodel "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/model"
	shareports "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/ports"
)

type recordingAppendSink struct {
	requests []shareports.AppendRequest
	receipts map[string]shareports.AppendResult
	digests  map[string]string
}

func (s *recordingAppendSink) Append(_ context.Context, request shareports.AppendRequest) (shareports.AppendResult, error) {
	if replay, ok := s.receipts[request.Fact.IdempotencyKey]; ok {
		replay.Replayed = true
		return replay, nil
	}
	s.requests = append(s.requests, request)
	result := shareports.AppendResult{Fact: request.Fact}
	s.receipts[request.Fact.IdempotencyKey] = result
	s.digests[request.Fact.IdempotencyKey] = request.CommandDigest
	return result, nil
}

type shareablePostReader struct{}

func (shareablePostReader) FindShareablePost(_ context.Context, postID string) (ShareablePostSlice, bool, error) {
	if postID == "post-published" {
		return ShareablePostSlice{PostID: postID, Status: "published"}, true, nil
	}
	return ShareablePostSlice{}, false, nil
}

func newOutboundShareServiceForTest() (*Service, *recordingAppendSink) {
	sink := &recordingAppendSink{receipts: map[string]shareports.AppendResult{}, digests: map[string]string{}}
	service := NewService(sink, shareablePostReader{})
	service.now = func() time.Time { return time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC) }
	service.newEventID = func() (string, error) { return "osf_event_1", nil }
	return service, sink
}

func TestAppendOutboundShareRequiresConfirmedDeliveryAndPersistsOnlyDigest(t *testing.T) {
	service, sink := newOutboundShareServiceForTest()
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "share-request-1")
	command := AppendOutboundShareCommand{
		PostID: "post-published", ActorDimension: sharemodel.ActorDimensionPersona,
		ActorID: "persona-1", Channel: "system_share_sheet", DestinationKind: "contact",
		Destination: "recipient@example.com", ReferralID: "referral-1",
		DeliverySucceeded: true, ProviderReceiptID: "provider-receipt-1",
	}
	result, err := service.AppendOutboundShare(ctx, command)
	if err != nil {
		t.Fatalf("append outbound share: %v", err)
	}
	if result.EventID != "osf_event_1" || result.Replayed {
		t.Fatalf("unexpected result: %#v", result)
	}
	if len(sink.requests) != 1 {
		t.Fatalf("append count=%d, want 1", len(sink.requests))
	}
	fact := sink.requests[0].Fact
	if fact.DestinationDigest == "" || fact.DestinationDigest == command.Destination {
		t.Fatalf("destination must only persist as irreversible digest: %#v", fact)
	}
	if string(sink.requests[0].Outbox.Payload) == "" {
		t.Fatal("outbox payload is required")
	}

	replayed, err := service.AppendOutboundShare(ctx, command)
	if err != nil || !replayed.Replayed || replayed.EventID != result.EventID {
		t.Fatalf("idempotent replay mismatch result=%#v err=%v", replayed, err)
	}
	if len(sink.requests) != 1 {
		t.Fatalf("replay created another fact: %d", len(sink.requests))
	}
}

func TestAppendOutboundShareRejectsUnconfirmedOrMissingPost(t *testing.T) {
	service, _ := newOutboundShareServiceForTest()
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "share-request-2")
	base := AppendOutboundShareCommand{
		PostID: "post-published", ActorDimension: sharemodel.ActorDimensionDevice,
		ActorID: "device-1", Channel: "system_share_sheet", DestinationKind: "unknown",
		ReferralID: "referral-2", ProviderReceiptID: "provider-receipt-2",
	}
	if _, err := service.AppendOutboundShare(ctx, base); err == nil {
		t.Fatal("unconfirmed delivery must be rejected")
	}
	base.DeliverySucceeded = true
	base.PostID = "missing"
	if _, err := service.AppendOutboundShare(ctx, base); err == nil {
		t.Fatal("missing Post reference must be rejected")
	}
}
