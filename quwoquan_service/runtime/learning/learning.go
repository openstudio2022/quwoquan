package runtimelearning

import (
	"context"
	"encoding/json"
	"errors"
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
}

type Recorder interface {
	RecordEvent(ctx context.Context, event Event) error
	RecordScorecard(ctx context.Context, scorecard Scorecard) error
}

// NoopRecorder allows services to integrate runtime-learning before backend readiness.
type NoopRecorder struct{}

func (NoopRecorder) RecordEvent(_ context.Context, _ Event) error         { return nil }
func (NoopRecorder) RecordScorecard(_ context.Context, _ Scorecard) error { return nil }

// BufferedRecorder buffers events and scorecards, flushing to a sink periodically.
type BufferedRecorder struct {
	mu         sync.Mutex
	flushMu    sync.Mutex
	stopOnce   sync.Once
	events     []Event
	scorecards []Scorecard
	sink       Sink
	logger     *slog.Logger
	flushSize  int
	flushEvery time.Duration
	flushNow   chan struct{}
	done       chan struct{}
	stopped    bool
}

var ErrRecorderStopped = errors.New("learning recorder is stopped")

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
		flushNow:   make(chan struct{}, 1),
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
	if r.stopped {
		r.mu.Unlock()
		return ErrRecorderStopped
	}
	r.events = append(r.events, event)
	shouldFlush := len(r.events) >= r.flushSize
	r.mu.Unlock()

	if shouldFlush {
		r.requestFlush()
	}
	return nil
}

func (r *BufferedRecorder) RecordScorecard(_ context.Context, scorecard Scorecard) error {
	r.mu.Lock()
	if r.stopped {
		r.mu.Unlock()
		return ErrRecorderStopped
	}
	r.scorecards = append(r.scorecards, scorecard)
	shouldFlush := len(r.scorecards) >= r.flushSize
	r.mu.Unlock()

	if shouldFlush {
		r.requestFlush()
	}
	return nil
}

// Stop flushes remaining data and stops the background loop.
func (r *BufferedRecorder) Stop() {
	r.stopOnce.Do(func() {
		r.mu.Lock()
		r.stopped = true
		r.mu.Unlock()
		close(r.done)
		r.flush()
	})
}

func (r *BufferedRecorder) requestFlush() {
	select {
	case r.flushNow <- struct{}{}:
	default:
		// 已有 flush 信号待处理；单个信号会 drain 当前全部缓冲。
	}
}

func (r *BufferedRecorder) flushLoop() {
	ticker := time.NewTicker(r.flushEvery)
	defer ticker.Stop()

	for {
		select {
		case <-r.done:
			return
		case <-r.flushNow:
			r.flush()
		case <-ticker.C:
			r.flush()
		}
	}
}

func (r *BufferedRecorder) flush() {
	// 阈值触发、周期触发与 Stop 可能并发；串行化 drain/flush/requeue，
	// 避免同一批次乱序或失败批次被后续 flush 越过。
	r.flushMu.Lock()
	defer r.flushMu.Unlock()

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
			// Sink 采用 at-least-once 语义；推荐事件以确定性 eventId 去重。
			// 失败批次必须回到队首，禁止瞬时 Mongo 故障静默丢训练事实。
			r.mu.Lock()
			r.events = append(events, r.events...)
			r.mu.Unlock()
		}
	}
	if len(scorecards) > 0 {
		if err := r.sink.FlushScorecards(ctx, scorecards); err != nil {
			r.logger.Error("learning: flush scorecards failed", slog.String("error", err.Error()))
			r.mu.Lock()
			r.scorecards = append(scorecards, r.scorecards...)
			r.mu.Unlock()
		}
	}
}
