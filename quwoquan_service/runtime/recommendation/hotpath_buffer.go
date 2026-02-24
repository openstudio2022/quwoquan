package recommendation

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

const (
	defaultBufferSize    = 4096
	defaultFlushInterval = 50 * time.Millisecond
	defaultFlushBatch    = 64
	flushTimeout         = 5 * time.Second
)

// BufferedHotPath wraps HotPath with an async write channel.
// Behavior signals are queued and flushed in batches, removing
// all Redis write latency from the request hot path.
type BufferedHotPath struct {
	inner  *HotPath
	ch     chan BehaviorSignal
	logger *slog.Logger
	wg     sync.WaitGroup
	stopCh chan struct{}

	bufferSize    int
	flushInterval time.Duration
	flushBatch    int
}

// BufferedOption configures BufferedHotPath.
type BufferedOption func(*BufferedHotPath)

func WithBufferSize(n int) BufferedOption {
	return func(b *BufferedHotPath) {
		if n > 0 {
			b.bufferSize = n
		}
	}
}

func WithFlushInterval(d time.Duration) BufferedOption {
	return func(b *BufferedHotPath) {
		if d > 0 {
			b.flushInterval = d
		}
	}
}

func WithBufferLogger(l *slog.Logger) BufferedOption {
	return func(b *BufferedHotPath) { b.logger = l }
}

func NewBufferedHotPath(inner *HotPath, opts ...BufferedOption) *BufferedHotPath {
	b := &BufferedHotPath{
		inner:         inner,
		stopCh:        make(chan struct{}),
		bufferSize:    defaultBufferSize,
		flushInterval: defaultFlushInterval,
		flushBatch:    defaultFlushBatch,
	}
	for _, opt := range opts {
		opt(b)
	}
	b.ch = make(chan BehaviorSignal, b.bufferSize)
	b.wg.Add(1)
	go b.flushLoop()
	return b
}

// ProcessSignal enqueues a signal for async processing.
// Returns immediately; drops if buffer is full (back-pressure).
func (b *BufferedHotPath) ProcessSignal(_ context.Context, signal BehaviorSignal) error {
	select {
	case b.ch <- signal:
		return nil
	default:
		if b.logger != nil {
			b.logger.Warn("rec.hotpath.buffer_full",
				slog.String("userId", signal.UserID),
				slog.Int("bufferSize", b.bufferSize))
		}
		return nil
	}
}

// ProcessSignalBatch enqueues all signals for async processing.
func (b *BufferedHotPath) ProcessSignalBatch(_ context.Context, signals []BehaviorSignal) error {
	for _, s := range signals {
		select {
		case b.ch <- s:
		default:
			if b.logger != nil {
				b.logger.Warn("rec.hotpath.buffer_full",
					slog.String("userId", s.UserID),
					slog.Int("dropped", len(signals)))
			}
			return nil
		}
	}
	return nil
}

// GetSessionState delegates to the inner HotPath (reads are not buffered).
func (b *BufferedHotPath) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	return b.inner.GetSessionState(ctx, userID, sessionID)
}

// IsExposed delegates to the inner HotPath.
func (b *BufferedHotPath) IsExposed(ctx context.Context, userID, sessionID, contentID string) (bool, error) {
	return b.inner.IsExposed(ctx, userID, sessionID, contentID)
}

// Stop drains the buffer and waits for the flush loop to finish.
func (b *BufferedHotPath) Stop() {
	close(b.stopCh)
	b.wg.Wait()
}

func (b *BufferedHotPath) flushLoop() {
	defer b.wg.Done()
	ticker := time.NewTicker(b.flushInterval)
	defer ticker.Stop()

	batch := make([]BehaviorSignal, 0, b.flushBatch)

	for {
		select {
		case signal, ok := <-b.ch:
			if !ok {
				return
			}
			batch = append(batch, signal)
			if len(batch) >= b.flushBatch {
				b.flush(batch)
				batch = batch[:0]
			}

		case <-ticker.C:
			if len(batch) > 0 {
				b.flush(batch)
				batch = batch[:0]
			}

		case <-b.stopCh:
			close(b.ch)
			for signal := range b.ch {
				batch = append(batch, signal)
			}
			if len(batch) > 0 {
				b.flush(batch)
			}
			return
		}
	}
}

func (b *BufferedHotPath) flush(batch []BehaviorSignal) {
	ctx, cancel := context.WithTimeout(context.Background(), flushTimeout)
	defer cancel()

	if err := b.inner.ProcessSignalBatch(ctx, batch); err != nil {
		if b.logger != nil {
			b.logger.Error("rec.hotpath.flush_error",
				slog.String("err", err.Error()),
				slog.Int("batchSize", len(batch)))
		}
	}
}
