package runtimelearning

import (
	"context"
	"encoding/json"
	"log/slog"
	"sync"
	"time"
)

type Event struct {
	EventID     string
	EventType   string
	Scenario    string
	OccurredAt  string
	UserID      string
	PersonaID   string
	PageID      string
	TraceID     string
	CausationID string
	TargetID    string
	Labels      map[string]string
	Context     map[string]any
}

type Scorecard struct {
	ScorecardID string
	RunID       string
	Score       float64
	Comment     string
	Version     string
}

type Recorder interface {
	RecordEvent(ctx context.Context, event Event) error
	RecordScorecard(ctx context.Context, scorecard Scorecard) error
}

// NoopRecorder allows services to integrate runtime-learning before backend readiness.
type NoopRecorder struct{}

func (NoopRecorder) RecordEvent(_ context.Context, _ Event) error       { return nil }
func (NoopRecorder) RecordScorecard(_ context.Context, _ Scorecard) error { return nil }

// BufferedRecorder buffers events and scorecards, flushing to a sink periodically.
type BufferedRecorder struct {
	mu         sync.Mutex
	events     []Event
	scorecards []Scorecard
	sink       Sink
	logger     *slog.Logger
	flushSize  int
	flushEvery time.Duration
	done       chan struct{}
}

// Sink defines where learning data is persisted.
type Sink interface {
	FlushEvents(ctx context.Context, events []Event) error
	FlushScorecards(ctx context.Context, scorecards []Scorecard) error
}

// LogSink writes events as structured log lines (for dev/bootstrap).
type LogSink struct {
	Logger *slog.Logger
}

func (s *LogSink) FlushEvents(_ context.Context, events []Event) error {
	for _, e := range events {
		payload, _ := json.Marshal(e)
		s.Logger.Info("learning.event", slog.String("payload", string(payload)))
	}
	return nil
}

func (s *LogSink) FlushScorecards(_ context.Context, scorecards []Scorecard) error {
	for _, sc := range scorecards {
		payload, _ := json.Marshal(sc)
		s.Logger.Info("learning.scorecard", slog.String("payload", string(payload)))
	}
	return nil
}

type BufferedRecorderOption func(*BufferedRecorder)

func WithFlushSize(n int) BufferedRecorderOption {
	return func(r *BufferedRecorder) { r.flushSize = n }
}

func WithFlushInterval(d time.Duration) BufferedRecorderOption {
	return func(r *BufferedRecorder) { r.flushEvery = d }
}

func NewBufferedRecorder(sink Sink, logger *slog.Logger, opts ...BufferedRecorderOption) *BufferedRecorder {
	r := &BufferedRecorder{
		sink:       sink,
		logger:     logger,
		flushSize:  100,
		flushEvery: 5 * time.Second,
		done:       make(chan struct{}),
	}
	for _, o := range opts {
		o(r)
	}
	go r.flushLoop()
	return r
}

func (r *BufferedRecorder) RecordEvent(_ context.Context, event Event) error {
	r.mu.Lock()
	r.events = append(r.events, event)
	shouldFlush := len(r.events) >= r.flushSize
	r.mu.Unlock()

	if shouldFlush {
		r.flush()
	}
	return nil
}

func (r *BufferedRecorder) RecordScorecard(_ context.Context, scorecard Scorecard) error {
	r.mu.Lock()
	r.scorecards = append(r.scorecards, scorecard)
	shouldFlush := len(r.scorecards) >= r.flushSize
	r.mu.Unlock()

	if shouldFlush {
		r.flush()
	}
	return nil
}

// Stop flushes remaining data and stops the background loop.
func (r *BufferedRecorder) Stop() {
	close(r.done)
	r.flush()
}

func (r *BufferedRecorder) flushLoop() {
	ticker := time.NewTicker(r.flushEvery)
	defer ticker.Stop()

	for {
		select {
		case <-r.done:
			return
		case <-ticker.C:
			r.flush()
		}
	}
}

func (r *BufferedRecorder) flush() {
	r.mu.Lock()
	events := r.events
	scorecards := r.scorecards
	r.events = nil
	r.scorecards = nil
	r.mu.Unlock()

	ctx := context.Background()
	if len(events) > 0 {
		if err := r.sink.FlushEvents(ctx, events); err != nil {
			r.logger.Error("learning: flush events failed", slog.String("error", err.Error()))
		}
	}
	if len(scorecards) > 0 {
		if err := r.sink.FlushScorecards(ctx, scorecards); err != nil {
			r.logger.Error("learning: flush scorecards failed", slog.String("error", err.Error()))
		}
	}
}
