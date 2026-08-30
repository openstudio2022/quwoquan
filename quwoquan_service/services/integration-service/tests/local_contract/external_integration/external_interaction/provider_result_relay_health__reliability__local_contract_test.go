// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001

package local_contract

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"strings"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/resultrelay"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

// programmableRelayOutboxStore 让每个用例只声明一处失败注入，
// 从而把「哪一步失败」与「租约是否被归还」一一对应上。
type programmableRelayOutboxStore struct {
	mu               sync.Mutex
	record           reliabletask.ExternalInteractionResultOutboxRecord
	recordsRemaining int
	leaseErr         error
	acknowledged     bool
	ackErr           error
	leaseCalls       int
	releaseCalls     int
	ackCalls         int
	observed         chan int
}

func (store *programmableRelayOutboxStore) LeaseNextExternalInteractionResultOutbox(
	context.Context,
	string,
	time.Duration,
) (reliabletask.ExternalInteractionResultOutboxRecord, bool, error) {
	store.mu.Lock()
	store.leaseCalls++
	call := store.leaseCalls
	remaining := store.recordsRemaining
	if remaining > 0 {
		store.recordsRemaining--
	}
	leaseErr := store.leaseErr
	record := store.record
	store.mu.Unlock()
	if store.observed != nil {
		select {
		case store.observed <- call:
		default:
		}
	}
	if leaseErr != nil {
		return reliabletask.ExternalInteractionResultOutboxRecord{}, false, leaseErr
	}
	if remaining <= 0 {
		return reliabletask.ExternalInteractionResultOutboxRecord{}, false, nil
	}
	return record, true, nil
}

func (store *programmableRelayOutboxStore) AcknowledgeExternalInteractionResultOutbox(
	context.Context,
	string,
	string,
) (bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.ackCalls++
	return store.acknowledged, store.ackErr
}

func (store *programmableRelayOutboxStore) ReleaseExternalInteractionResultOutboxLease(
	context.Context,
	string,
	string,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.releaseCalls++
	return nil
}

func (store *programmableRelayOutboxStore) counters() (int, int, int) {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.leaseCalls, store.releaseCalls, store.ackCalls
}

// programmableRelayTransport 只按用例注入 append/retention 两段失败，
// 不承载任何 provider 凭据：中继重放只能重放传输。
type programmableRelayTransport struct {
	mu           sync.Mutex
	appendErr    error
	retentionErr error
	messages     []runtimemessaging.DurableMessage
}

func (transport *programmableRelayTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.mu.Lock()
	defer transport.mu.Unlock()
	transport.messages = append(transport.messages, message)
	if transport.appendErr != nil {
		return "", transport.appendErr
	}
	return "1-0", nil
}

func (transport *programmableRelayTransport) SetDurableRetention(
	context.Context,
	string,
	time.Duration,
) error {
	transport.mu.Lock()
	defer transport.mu.Unlock()
	return transport.retentionErr
}

func (transport *programmableRelayTransport) appendCount() int {
	transport.mu.Lock()
	defer transport.mu.Unlock()
	return len(transport.messages)
}

func completeRelayOutboxRecord() reliabletask.ExternalInteractionResultOutboxRecord {
	return reliabletask.ExternalInteractionResultOutboxRecord{
		EventID:      "attempt-relay-health-001",
		RequestID:    "request-relay-health-001",
		Operation:    reliabletask.ExternalInteractionOperationSmsOTP,
		ResultStatus: reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:     "aliyun_sms",
		ProviderRequestDigest: integrationsupport.CanonicalTestSHA256(
			"aliyun_sms:provider-request-relay-health-001",
		),
		RecoveryAction: "none",
		OccurredAt:     time.Date(2026, 8, 20, 8, 0, 0, 0, time.UTC),
	}
}

func silentRelayLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// 中继的两个依赖都是必需的：缺 outbox 或缺传输时必须在装配期失败，
// 不能构造出一个「看起来在跑但永远发不出回执」的中继。
func TestResultRelayRequiresOutboxAndTransportAtComposition(t *testing.T) {
	if _, err := resultrelay.New(nil, &programmableRelayTransport{}, silentRelayLogger()); err == nil ||
		err.Error() != "external interaction result relay requires an outbox store" {
		t.Fatalf("missing outbox store must fail composition: %v", err)
	}
	if _, err := resultrelay.New(
		&programmableRelayOutboxStore{},
		nil,
		silentRelayLogger(),
	); err == nil ||
		err.Error() != "external interaction result relay requires a message transport" {
		t.Fatalf("missing transport must fail composition: %v", err)
	}

	var absent *resultrelay.Relay
	worked, err := absent.ProcessOnce(context.Background())
	if worked || err == nil ||
		err.Error() != "external interaction result relay is not configured" {
		t.Fatalf("unwired relay must fail closed: worked=%v err=%v", worked, err)
	}
	if err := absent.Healthy(context.Background(), time.Second); err == nil {
		t.Fatal("unwired relay must report unhealthy")
	}
}

// ProcessOnce 的每一步失败都必须归还租约或如实报错，绝不能静默确认：
// 回执一旦被误确认就永久丢失，App 侧的验证码状态会永远停在受理态。
func TestResultRelayProcessOnceFailureLeavesOutboxReplayable(t *testing.T) {
	for _, testCase := range []struct {
		name         string
		store        func(*programmableRelayOutboxStore)
		transport    func(*programmableRelayTransport)
		wantWorked   bool
		wantErr      string
		wantReleases int
		wantAppends  int
	}{
		{
			name: "lease failure is not work",
			store: func(store *programmableRelayOutboxStore) {
				store.leaseErr = errors.New("outbox lease is unavailable")
			},
			wantErr: "outbox lease is unavailable",
		},
		{
			name: "incomplete record releases the lease",
			store: func(store *programmableRelayOutboxStore) {
				store.record.ProviderRequestDigest = ""
			},
			wantWorked:   true,
			wantErr:      "external interaction result outbox record is incomplete",
			wantReleases: 1,
		},
		{
			name: "append failure releases the lease",
			transport: func(transport *programmableRelayTransport) {
				transport.appendErr = errors.New("durable stream is unavailable")
			},
			wantWorked:   true,
			wantErr:      "durable stream is unavailable",
			wantReleases: 1,
			wantAppends:  1,
		},
		{
			name: "retention failure is reported after append",
			transport: func(transport *programmableRelayTransport) {
				transport.retentionErr = errors.New("retention command rejected")
			},
			wantWorked:  true,
			wantErr:     "set external interaction result retention",
			wantAppends: 1,
		},
		{
			name: "acknowledge failure is reported",
			store: func(store *programmableRelayOutboxStore) {
				store.ackErr = errors.New("acknowledge command rejected")
			},
			wantWorked:  true,
			wantErr:     "acknowledge external interaction result outbox",
			wantAppends: 1,
		},
		{
			name: "lost lease is reported instead of silently acknowledged",
			store: func(store *programmableRelayOutboxStore) {
				store.acknowledged = false
			},
			wantWorked:  true,
			wantErr:     "external interaction result outbox relay lease lost",
			wantAppends: 1,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := &programmableRelayOutboxStore{
				record:           completeRelayOutboxRecord(),
				recordsRemaining: 1,
				acknowledged:     true,
			}
			if testCase.store != nil {
				testCase.store(store)
			}
			transport := &programmableRelayTransport{}
			if testCase.transport != nil {
				testCase.transport(transport)
			}
			relay, err := resultrelay.New(store, transport, silentRelayLogger())
			if err != nil {
				t.Fatalf("compose relay: %v", err)
			}
			worked, err := relay.ProcessOnce(context.Background())
			if worked != testCase.wantWorked || err == nil ||
				!strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("worked=%v err=%v, want work=%v err~=%q", worked, err, testCase.wantWorked, testCase.wantErr)
			}
			_, releases, _ := store.counters()
			if releases != testCase.wantReleases {
				t.Fatalf("release count=%d, want=%d", releases, testCase.wantReleases)
			}
			if transport.appendCount() != testCase.wantAppends {
				t.Fatalf("append count=%d, want=%d", transport.appendCount(), testCase.wantAppends)
			}
			if err := relay.Healthy(context.Background(), 0); err == nil {
				t.Fatal("a failed scan must be visible on the health surface")
			}
			if err := relay.CheckSMSOTPResultRelayReadiness(context.Background()); err == nil {
				t.Fatal("a failed scan must block SMS OTP readiness")
			}
		})
	}
}

// 空扫描也是一次成功心跳：没有回执待发时中继必须报告健康，
// 否则登录就绪会在系统完全正常时被判成不可用。
func TestResultRelayEmptyScanRefreshesHealthHeartbeat(t *testing.T) {
	store := &programmableRelayOutboxStore{acknowledged: true}
	transport := &programmableRelayTransport{}
	relay, err := resultrelay.New(store, transport, silentRelayLogger())
	if err != nil {
		t.Fatalf("compose relay: %v", err)
	}
	if err := relay.Healthy(context.Background(), time.Second); err == nil ||
		!strings.Contains(err.Error(), "heartbeat is stale") {
		t.Fatalf("never-scanned relay must report a stale heartbeat: %v", err)
	}

	worked, err := relay.ProcessOnce(context.Background())
	if worked || err != nil {
		t.Fatalf("empty scan = (%v, %v), want no work without error", worked, err)
	}
	if err := relay.Healthy(context.Background(), 0); err != nil {
		t.Fatalf("empty scan must refresh the heartbeat: %v", err)
	}
	if err := relay.CheckSMSOTPResultRelayReadiness(context.Background()); err != nil {
		t.Fatalf("healthy relay must pass SMS OTP readiness: %v", err)
	}
	if transport.appendCount() != 0 {
		t.Fatalf("empty scan must not emit any result event: %d", transport.appendCount())
	}
}

// Run 是常驻循环：有回执时连续处理，空扫描后按 poll 间隔等待，
// 且必须在 context 取消时干净退出，不留悬挂 goroutine。
func TestResultRelayRunDrainsOutboxThenExitsOnCancel(t *testing.T) {
	store := &programmableRelayOutboxStore{
		record:           completeRelayOutboxRecord(),
		recordsRemaining: 2,
		acknowledged:     true,
		observed:         make(chan int, 8),
	}
	transport := &programmableRelayTransport{}
	relay, err := resultrelay.New(store, transport, silentRelayLogger())
	if err != nil {
		t.Fatalf("compose relay: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	stopped := make(chan struct{})
	go func() {
		relay.Run(ctx)
		close(stopped)
	}()
	awaitRelayLeaseCalls(t, store, 3)
	cancel()
	awaitRelayStop(t, stopped)

	if transport.appendCount() != 2 {
		t.Fatalf("Run must emit one event per leased record: %d", transport.appendCount())
	}
	_, _, acks := store.counters()
	if acks != 2 {
		t.Fatalf("Run must acknowledge every relayed record: %d", acks)
	}
	if err := relay.Healthy(context.Background(), 0); err != nil {
		t.Fatalf("drained relay must stay healthy: %v", err)
	}
}

// 持续失败时 Run 必须退避重试而不是打爆依赖，同时把最后一次错误留在
// 健康面上；取消 context 仍然必须立即退出。
func TestResultRelayRunBacksOffOnRepeatedFailureAndExitsOnCancel(t *testing.T) {
	store := &programmableRelayOutboxStore{
		record:       completeRelayOutboxRecord(),
		leaseErr:     errors.New("outbox lease is unavailable"),
		acknowledged: true,
		observed:     make(chan int, 8),
	}
	transport := &programmableRelayTransport{}
	relay, err := resultrelay.New(store, transport, silentRelayLogger())
	if err != nil {
		t.Fatalf("compose relay: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	stopped := make(chan struct{})
	go func() {
		relay.Run(ctx)
		close(stopped)
	}()
	awaitRelayLeaseCalls(t, store, 2)
	cancel()
	awaitRelayStop(t, stopped)

	if transport.appendCount() != 0 {
		t.Fatalf("failed lease must not emit any result event: %d", transport.appendCount())
	}
	if err := relay.Healthy(context.Background(), 0); err == nil ||
		!strings.Contains(err.Error(), "outbox lease is unavailable") {
		t.Fatalf("repeated failure must stay visible on the health surface: %v", err)
	}
}

func awaitRelayLeaseCalls(t *testing.T, store *programmableRelayOutboxStore, want int) {
	t.Helper()
	deadline := time.After(10 * time.Second)
	for range want {
		select {
		case <-store.observed:
		case <-deadline:
			leases, _, _ := store.counters()
			t.Fatalf("relay loop only reached %d lease call(s), want %d", leases, want)
		}
	}
}

func awaitRelayStop(t *testing.T, stopped <-chan struct{}) {
	t.Helper()
	select {
	case <-stopped:
	case <-time.After(10 * time.Second):
		t.Fatal("Run must return once the context is cancelled")
	}
}
