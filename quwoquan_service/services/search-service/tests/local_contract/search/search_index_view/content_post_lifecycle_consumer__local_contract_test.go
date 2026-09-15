package local_contract_test

import (
	"context"
	"errors"
	"io"
	"log/slog"
	messaging "quwoquan_service/runtime/messaging"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 此测试只证明投递编排，非Content wire/安全投影/生产装配证明。
type lifecycleTransport struct {
	messaging.DurableDeliveryTransport
	reclaimed, fresh              []messaging.StreamDelivery
	acked                         []string
	ackErr                        error
	groupErr, reclaimErr, readErr error
	read                          func(context.Context) ([]messaging.StreamDelivery, error)
}

func (t *lifecycleTransport) EnsureDurableConsumerGroup(context.Context, string, string, string) error {
	return t.groupErr
}
func (t *lifecycleTransport) ReclaimDurable(context.Context, string, string, string, time.Duration, string, int64) ([]messaging.StreamDelivery, string, error) {
	return t.reclaimed, "0-0", t.reclaimErr
}
func (t *lifecycleTransport) ReadDurable(ctx context.Context, _ messaging.StreamReadRequest) ([]messaging.StreamDelivery, error) {
	if t.read != nil {
		return t.read(ctx)
	}
	return t.fresh, t.readErr
}
func (t *lifecycleTransport) AckDurable(_ context.Context, _, _ string, ids ...string) error {
	if t.ackErr != nil {
		return t.ackErr
	}
	t.acked = append(t.acked, ids...)
	return nil
}

type lifecycleHandler struct {
	calls int
	err   error
}

func (h *lifecycleHandler) ApplyContentPostDelivery(context.Context, messaging.StreamDelivery) error {
	h.calls++
	return h.err
}
func TestContentLifecycleDeliveryRequiresHandlerAndPreservesPending(t *testing.T) {
	ctx := context.Background()
	transport := &lifecycleTransport{fresh: []messaging.StreamDelivery{{Stream: "events.content.post_lifecycle", ID: "1-0"}}}
	if _, err := app.NewContentPostLifecycleConsumer(transport, nil, "search-content", "one"); err == nil {
		t.Fatal("missing generated decoder handler accepted")
	}
	handler := &lifecycleHandler{err: errors.New("unknown or unimplemented payload")}
	consumer, err := app.NewContentPostLifecycleConsumer(transport, handler, "search-content", "one")
	if err != nil {
		t.Fatal(err)
	}
	n, err := consumer.ProcessOnce(ctx)
	if err == nil || n != 0 || len(transport.acked) != 0 {
		t.Fatal("failed application acknowledged", n, err, transport.acked)
	}
	handler.err = nil
	transport.reclaimed = transport.fresh
	n, err = consumer.ProcessOnce(ctx)
	if err != nil || n != 1 || len(transport.acked) != 1 || handler.calls != 2 {
		t.Fatal("reclaim/fresh duplicate applied", n, err, handler.calls)
	}
	transport.ackErr = errors.New("ack unavailable")
	n, err = consumer.ProcessOnce(ctx)
	if err == nil || n != 0 {
		t.Fatal("ack failure reported as success")
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthRetainsEachDelivery(t *testing.T) {
	for _, ackFailure := range []bool{false, true} {
		t.Run(fmtBool(ackFailure), func(t *testing.T) {
			transport := &lifecycleTransport{}
			handler := &lifecycleHandler{}
			consumer, err := app.NewContentPostLifecycleConsumer(transport, handler, "health", "one")
			if err != nil {
				t.Fatal(err)
			}
			if consumer.Healthy(15*time.Second) == nil {
				t.Fatal("ready before first scan")
			}
			if _, err = consumer.ProcessOnce(context.Background()); err != nil {
				t.Fatal(err)
			}
			if err = consumer.Healthy(15 * time.Second); err != nil {
				t.Fatal(err)
			}
			secret := errors.New("private payload author@example.invalid")
			if ackFailure {
				transport.ackErr = secret
			} else {
				handler.err = secret
			}
			for _, id := range []string{"1-0", "2-0"} {
				transport.fresh = []messaging.StreamDelivery{{Stream: "events.content.post_lifecycle", ID: id}}
				if _, err = consumer.ProcessOnce(context.Background()); err == nil {
					t.Fatal("failure lost")
				}
			}
			handler.err, transport.ackErr, transport.fresh = nil, nil, nil
			transport.readErr = errors.New("transient read unavailable")
			if _, err = consumer.ProcessOnce(context.Background()); err == nil {
				t.Fatal("read failure lost")
			}
			transport.readErr = nil
			if _, err = consumer.ProcessOnce(context.Background()); err != nil {
				t.Fatal(err)
			}
			if err = consumer.Healthy(15 * time.Second); err == nil || strings.Contains(err.Error(), "private") || strings.Contains(err.Error(), "author@") {
				t.Fatal("empty scan cleared failures or leaked payload", err)
			}
			for i, id := range []string{"1-0", "2-0"} {
				transport.reclaimed = []messaging.StreamDelivery{{Stream: "events.content.post_lifecycle", ID: id}}
				if n, err := consumer.ProcessOnce(context.Background()); err != nil || n != 1 {
					t.Fatal(n, err)
				}
				if got := consumer.Healthy(15 * time.Second); (got == nil) != (i == 1) {
					t.Fatal("one success cleared other delivery", got)
				}
			}
		})
	}
}

func fmtBool(ack bool) string {
	if ack {
		return "ack"
	}
	return "handler"
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthTransportRecovery(t *testing.T) {
	for _, stage := range []string{"group", "reclaim", "read"} {
		t.Run(stage, func(t *testing.T) {
			transport := &lifecycleTransport{}
			consumer, _ := app.NewContentPostLifecycleConsumer(transport, &lifecycleHandler{}, "health", "one")
			failure := errors.New("sensitive transport failure")
			switch stage {
			case "group":
				transport.groupErr = failure
			case "reclaim":
				transport.reclaimErr = failure
			case "read":
				transport.readErr = failure
			}
			if _, err := consumer.ProcessOnce(context.Background()); err == nil {
				t.Fatal("transport failure lost")
			}
			if err := consumer.Healthy(15 * time.Second); err == nil || strings.Contains(err.Error(), "sensitive") {
				t.Fatal(err)
			}
			transport.groupErr, transport.reclaimErr, transport.readErr = nil, nil, nil
			if _, err := consumer.ProcessOnce(context.Background()); err != nil {
				t.Fatal(err)
			}
			if err := consumer.Healthy(15 * time.Second); err != nil {
				t.Fatal(err)
			}
		})
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthClockCancellationAndRace(t *testing.T) {
	var seconds atomic.Int64
	clock := func() time.Time { return time.Unix(1700000000+seconds.Load(), 0) }
	consumer, err := app.NewContentPostLifecycleConsumer(&lifecycleTransport{}, &lifecycleHandler{}, "health", "one", app.WithContentPostConsumerClock(clock))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	seconds.Store(16)
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("stale scan ready")
	}
	if consumer.Healthy(0) == nil {
		t.Fatal("invalid bound accepted")
	}
	var wg sync.WaitGroup
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				_ = consumer.Healthy(15 * time.Second)
			}
		}()
	}
	for i := 0; i < 100; i++ {
		if _, err = consumer.ProcessOnce(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	wg.Wait()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = consumer.ProcessOnce(ctx); err == nil {
		t.Fatal("cancelled scan accepted")
	}
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("cancelled scan ready")
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthStoppedWorker(t *testing.T) {
	entered, done := make(chan struct{}), make(chan struct{})
	transport := &lifecycleTransport{read: func(ctx context.Context) ([]messaging.StreamDelivery, error) {
		close(entered)
		<-ctx.Done()
		return nil, ctx.Err()
	}}
	consumer, _ := app.NewContentPostLifecycleConsumer(transport, &lifecycleHandler{}, "health", "one")
	ctx, cancel := context.WithCancel(context.Background())
	go func() { defer close(done); consumer.Run(ctx, slog.New(slog.NewTextHandler(io.Discard, nil))) }()
	<-entered
	cancel()
	<-done
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("stopped worker ready")
	}
	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("stopped worker restarted by scan")
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthRemembersUnprocessedBatch(t *testing.T) {
	rows := []messaging.StreamDelivery{{Stream: "events.content.post_lifecycle", ID: "1-0"}, {Stream: "events.content.post_lifecycle", ID: "2-0"}}
	transport := &lifecycleTransport{fresh: rows}
	handler := &lifecycleHandler{err: errors.New("unimplemented fence")}
	consumer, _ := app.NewContentPostLifecycleConsumer(transport, handler, "health", "one")
	if n, err := consumer.ProcessOnce(context.Background()); n != 0 || err == nil {
		t.Fatal(n, err)
	}
	transport.fresh = nil
	handler.err = nil
	transport.reclaimed = rows[:1]
	if n, err := consumer.ProcessOnce(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("unprocessed second delivery forgotten")
	}
	transport.reclaimed = rows[1:]
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := consumer.Healthy(15 * time.Second); err != nil {
		t.Fatal(err)
	}
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestContentLifecycleExecutionHealthInFlightStaleAndDeadline(t *testing.T) {
	var seconds atomic.Int64
	clock := func() time.Time { return time.Unix(1700000000+seconds.Load(), 0) }
	transport := &lifecycleTransport{}
	consumer, _ := app.NewContentPostLifecycleConsumer(transport, &lifecycleHandler{}, "health", "one", app.WithContentPostConsumerClock(clock))
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	entered, release, done := make(chan struct{}), make(chan struct{}), make(chan struct{})
	transport.read = func(context.Context) ([]messaging.StreamDelivery, error) {
		close(entered)
		<-release
		return nil, context.DeadlineExceeded
	}
	go func() { defer close(done); _, _ = consumer.ProcessOnce(context.Background()) }()
	<-entered
	seconds.Store(16)
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("hung scan fresh")
	}
	close(release)
	<-done
	if consumer.Healthy(15*time.Second) == nil {
		t.Fatal("deadline failure ready")
	}
	transport.read = nil
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := consumer.Healthy(15 * time.Second); err != nil {
		t.Fatal(err)
	}
}

func TestContentLifecycleForeignDeliveryCannotReachApplication(t *testing.T) {
	transport := &lifecycleTransport{fresh: []messaging.StreamDelivery{{Stream: "foreign", ID: "1-0"}}}
	handler := &lifecycleHandler{}
	consumer, err := app.NewContentPostLifecycleConsumer(transport, handler, "search-content", "one")
	if err != nil {
		t.Fatal(err)
	}
	if n, err := consumer.ProcessOnce(context.Background()); err == nil || n != 0 || handler.calls != 0 || len(transport.acked) != 0 {
		t.Fatal("foreign stream accepted")
	}
	var absent *app.ContentPostLifecycleConsumer
	if _, err := absent.ProcessOnce(context.Background()); err == nil {
		t.Fatal("nil consumer accepted")
	}
}
