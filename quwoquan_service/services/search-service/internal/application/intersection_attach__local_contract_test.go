package application

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

type intersectionReaderStub struct {
	facts map[string][]ObjectIntersectionFact
	errs  map[string]error
	mu    sync.Mutex
	calls []ObjectIntersectionQuery
}

func (s *intersectionReaderStub) ListObjectIntersections(
	_ context.Context,
	query ObjectIntersectionQuery,
) ([]ObjectIntersectionFact, error) {
	s.mu.Lock()
	s.calls = append(s.calls, query)
	s.mu.Unlock()
	if err := s.errs[query.ObjectID]; err != nil {
		return nil, err
	}
	return s.facts[query.ObjectID], nil
}

func (s *intersectionReaderStub) callCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.calls)
}

type attachObserverSpy struct {
	observations []IntersectionAttachObservation
}

func (s *attachObserverSpy) ObserveIntersectionAttach(
	observation IntersectionAttachObservation,
) {
	s.observations = append(s.observations, observation)
}

func TestIntersectionAttacherUsesCloudPrimaryTextAndDegradesPartially(t *testing.T) {
	reader := &intersectionReaderStub{
		facts: map[string][]ObjectIntersectionFact{
			"user-1": {{
				PrimaryText:       "你们都关注了光影摄影社",
				IntersectionID:    "ix-user-1",
				Dimension:         "relationship",
				IntersectionClass: "fact",
				SourceRef:         "sharedCircle",
			}},
		},
		errs: map[string]error{"circle-1": errors.New("dependency unavailable")},
	}
	observer := &attachObserverSpy{}
	attacher := NewIntersectionAttacher(
		reader,
		IntersectionAttacherConfig{
			Timeout: 100 * time.Millisecond, MaxHits: 3, MaxConcurrent: 2,
		},
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		observer,
	)

	response := attacher.Attach(
		context.Background(),
		"persona-1",
		rtsearch.RetrieveResponse{Hits: []rtsearch.RetrieveHit{
			{Target: rtsearch.TargetUser, ObjectID: "user-1"},
			{Target: rtsearch.TargetEntity, ObjectID: "homepage-1"},
			{Target: rtsearch.TargetCircle, ObjectID: "circle-1"},
		}},
	)

	if got := response.Hits[0].ConnectionState; got != ConnectionStateIntersectionLead {
		t.Fatalf("user connectionState=%q", got)
	}
	reason := response.Hits[0].IntersectionReason
	if reason == nil || reason.PrimaryText != "你们都关注了光影摄影社" ||
		reason.SourceRef != "sharedCircle" {
		t.Fatalf("cloud-authored reason not preserved: %#v", reason)
	}
	if got := response.Hits[1].ConnectionState; got != ConnectionStateUnconnected {
		t.Fatalf("empty intersection state=%q", got)
	}
	if got := response.Hits[2].ConnectionState; got != ConnectionStateUnconnected {
		t.Fatalf("degraded intersection state=%q", got)
	}
	if len(response.DegradeSignals) != 1 ||
		response.DegradeSignals[0].Code != intersectionAttachDegradeCode {
		t.Fatalf("missing bounded degrade signal: %#v", response.DegradeSignals)
	}
	if len(observer.observations) != 1 ||
		observer.observations[0].Status != "degraded" ||
		observer.observations[0].AttachedHits != 1 {
		t.Fatalf("attach observation=%#v", observer.observations)
	}
	if reader.callCount() != 3 {
		t.Fatalf("reader calls=%d want=3", reader.callCount())
	}
}

func TestIntersectionAttacherMapsOnlyDirectObjectEvidenceToConnected(t *testing.T) {
	reader := &intersectionReaderStub{
		facts: map[string][]ObjectIntersectionFact{
			"post-1": {{
				PrimaryText: "你关注的小林也评论过这篇内容",
				SourceRef:   "sharedFollowees",
				SourceRefs:  []string{"sharedFollowees", "coCommented"},
			}},
			"user-1": {{
				PrimaryText: "你们共同关注了光影摄影社",
				SourceRef:   "sharedFollowees",
				SourceRefs:  []string{"sharedFollowees"},
			}},
			"circle-1": {{
				PrimaryText: "你和小林都加入了光影摄影社",
				SourceRef:   "coMemberCircle",
				SourceRefs:  []string{"coMemberCircle"},
			}},
		},
	}
	attacher := NewIntersectionAttacher(
		reader,
		IntersectionAttacherConfig{MaxHits: 3},
		nil,
		nil,
	)

	output := attacher.Attach(
		context.Background(),
		"persona-1",
		rtsearch.RetrieveResponse{Hits: []rtsearch.RetrieveHit{
			{Target: rtsearch.TargetArticle, ObjectID: "post-1"},
			{Target: rtsearch.TargetUser, ObjectID: "user-1"},
			{Target: rtsearch.TargetCircle, ObjectID: "circle-1"},
		}},
	)

	if output.Hits[0].ConnectionState != ConnectionStateConnected {
		t.Fatalf("direct content interaction must be connected: %#v", output.Hits[0])
	}
	if output.Hits[1].ConnectionState != ConnectionStateIntersectionLead {
		t.Fatalf("shared followee must remain a lead: %#v", output.Hits[1])
	}
	if output.Hits[2].ConnectionState != ConnectionStateConnected {
		t.Fatalf("circle membership must be connected: %#v", output.Hits[2])
	}
}

func TestIntersectionAttacherDoesNotReadPrivateFactsForAnonymousViewer(t *testing.T) {
	reader := &intersectionReaderStub{}
	attacher := NewIntersectionAttacher(
		reader,
		IntersectionAttacherConfig{},
		nil,
		nil,
	)
	input := rtsearch.RetrieveResponse{Hits: []rtsearch.RetrieveHit{{
		Target: rtsearch.TargetUser, ObjectID: "user-1",
	}}}

	output := attacher.Attach(context.Background(), "", input)

	if reader.callCount() != 0 {
		t.Fatalf("anonymous search must not call intersection reader")
	}
	if output.Hits[0].ConnectionState != "" ||
		output.Hits[0].IntersectionReason != nil {
		t.Fatalf("anonymous response must not synthesize private state: %#v", output.Hits[0])
	}
}
