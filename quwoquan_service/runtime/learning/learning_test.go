package runtimelearning

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"sync"
	"testing"
	"time"
)

type spySink struct {
	mu         sync.Mutex
	events     []Event
	scorecards []Scorecard
}

func (s *spySink) FlushEvents(_ context.Context, events []Event) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, events...)
	return nil
}

func (s *spySink) FlushScorecards(_ context.Context, scorecards []Scorecard) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.scorecards = append(s.scorecards, scorecards...)
	return nil
}

func (s *spySink) eventCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.events)
}

func (s *spySink) scorecardCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.scorecards)
}

func TestNoopRecorder(t *testing.T) {
	r := NoopRecorder{}
	if err := r.RecordEvent(context.Background(), Event{EventID: "e1"}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if err := r.RecordScorecard(context.Background(), Scorecard{ScorecardID: "s1"}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestBufferedRecorder_FlushOnSize(t *testing.T) {
	sink := &spySink{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	r := NewBufferedRecorder(sink, logger, WithFlushSize(3), WithFlushInterval(10*time.Second))
	defer r.Stop()

	ctx := context.Background()
	r.RecordEvent(ctx, Event{EventID: "e1"})
	r.RecordEvent(ctx, Event{EventID: "e2"})
	r.RecordEvent(ctx, Event{EventID: "e3"})

	// Give the flush a moment to complete
	time.Sleep(50 * time.Millisecond)

	if sink.eventCount() != 3 {
		t.Errorf("expected 3 events flushed, got %d", sink.eventCount())
	}
}

func TestBufferedRecorder_FlushOnInterval(t *testing.T) {
	sink := &spySink{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	r := NewBufferedRecorder(sink, logger, WithFlushSize(100), WithFlushInterval(100*time.Millisecond))
	defer r.Stop()

	r.RecordEvent(context.Background(), Event{EventID: "e1"})
	time.Sleep(200 * time.Millisecond)

	if sink.eventCount() != 1 {
		t.Errorf("expected 1 event flushed on interval, got %d", sink.eventCount())
	}
}

func TestBufferedRecorder_FlushOnStop(t *testing.T) {
	sink := &spySink{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	r := NewBufferedRecorder(sink, logger, WithFlushSize(100), WithFlushInterval(10*time.Second))

	r.RecordEvent(context.Background(), Event{EventID: "e1"})
	r.RecordScorecard(context.Background(), Scorecard{ScorecardID: "s1"})
	r.Stop()
	r.Stop()

	if sink.eventCount() != 1 {
		t.Errorf("expected 1 event flushed on stop, got %d", sink.eventCount())
	}
	if sink.scorecardCount() != 1 {
		t.Errorf("expected 1 scorecard flushed on stop, got %d", sink.scorecardCount())
	}
	if err := r.RecordEvent(
		context.Background(),
		Event{EventID: "after-stop"},
	); !errors.Is(err, ErrRecorderStopped) {
		t.Fatalf("record after Stop must fail explicitly, got %v", err)
	}
}

func TestBufferedRecorder_Scorecards(t *testing.T) {
	sink := &spySink{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	r := NewBufferedRecorder(sink, logger, WithFlushSize(2))
	defer r.Stop()

	ctx := context.Background()
	r.RecordScorecard(ctx, Scorecard{ScorecardID: "s1", Score: 0.9})
	r.RecordScorecard(ctx, Scorecard{ScorecardID: "s2", Score: 0.8})

	time.Sleep(50 * time.Millisecond)

	if sink.scorecardCount() != 2 {
		t.Errorf("expected 2 scorecards, got %d", sink.scorecardCount())
	}
}

func TestBufferedRecorder_RequeuesFailedEventBatch(t *testing.T) {
	sink := &failOnceEventSink{}
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	recorder := NewBufferedRecorder(
		sink,
		logger,
		WithFlushSize(1),
		WithFlushInterval(20*time.Millisecond),
	)
	defer recorder.Stop()

	_ = recorder.RecordEvent(context.Background(), Event{EventID: "e1"})
	_ = recorder.RecordEvent(context.Background(), Event{EventID: "e2"})

	deadline := time.Now().Add(time.Second)
	for {
		sink.mu.Lock()
		completed := sink.calls >= 2 && len(sink.events) == 2
		sink.mu.Unlock()
		if completed || time.Now().After(deadline) {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	sink.mu.Lock()
	defer sink.mu.Unlock()
	if sink.calls != 2 {
		t.Fatalf("failed batch must be retried by the next flush, calls=%d", sink.calls)
	}
	if len(sink.events) != 2 ||
		sink.events[0].EventID != "e1" ||
		sink.events[1].EventID != "e2" {
		t.Fatalf("requeued batch must preserve order without loss: %+v", sink.events)
	}
}

type failOnceEventSink struct {
	mu     sync.Mutex
	calls  int
	events []Event
}

func (s *failOnceEventSink) FlushEvents(
	_ context.Context,
	events []Event,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.calls++
	if s.calls == 1 {
		return errors.New("transient sink failure")
	}
	s.events = append(s.events, events...)
	return nil
}

func (*failOnceEventSink) FlushScorecards(
	context.Context,
	[]Scorecard,
) error {
	return nil
}

func TestLogSink_NoError(t *testing.T) {
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
	sink := &LogSink{Logger: logger}

	if err := sink.FlushEvents(context.Background(), []Event{{EventID: "e1"}}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
	if err := sink.FlushScorecards(context.Background(), []Scorecard{{ScorecardID: "s1"}}); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}
