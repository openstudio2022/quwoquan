package application

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	messaging "quwoquan_service/runtime/messaging"
	"strings"
	"sync"
	"time"
)

// ContentPostDeliveryHandler是所属对象的入站处理边界，不声明/复制Content wire DTO。
// 实现必须先以正式生成的owning-event类型严格校验原始字段presence/null、完整来源、
// sourceVersion=同次envelope版本；fence控制身份不能按postId解码。之后经同域typed
// projection port完成投影与持久inbox。未知/未实现、安全资格不可证及对账失败必须error。
// nil只表示持久应用成功或有确切事实支撑的幂等结果，不是“已收到”。
type ContentPostDeliveryHandler interface {
	ApplyContentPostDelivery(context.Context, messaging.StreamDelivery) error
}

// ContentPostLifecycleConsumer仅编排既有durable transport；严格decoder与inbox/投影
// 仍由handler实现，缺handler不允许构造。此类型不是完整生产装配或安全准出证明。
type ContentPostLifecycleConsumer struct {
	transport       messaging.DurableDeliveryTransport
	handler         ContentPostDeliveryHandler
	group, consumer string
	scanMu          sync.Mutex
	mu              sync.RWMutex
	now             func() time.Time
	lastSuccess     time.Time
	scanError       string
	unresolved      map[string]struct{}
	stopped         bool
}

// 时钟在构造期固定，健康读取不推进消费；生产使用真实时间。
type ContentPostConsumerOption func(*ContentPostLifecycleConsumer)

func WithContentPostConsumerClock(now func() time.Time) ContentPostConsumerOption {
	return func(c *ContentPostLifecycleConsumer) { c.now = now }
}

const contentPostLifecycleStream = "events.content.post_lifecycle"

func NewContentPostLifecycleConsumer(transport messaging.DurableDeliveryTransport, handler ContentPostDeliveryHandler, group, consumer string, options ...ContentPostConsumerOption) (*ContentPostLifecycleConsumer, error) {
	if transport == nil || handler == nil || strings.TrimSpace(group) == "" || strings.TrimSpace(consumer) == "" {
		return nil, errors.New("Content Post lifecycle requires durable transport, strict handler and consumer identity")
	}
	c := &ContentPostLifecycleConsumer{transport: transport, handler: handler, group: strings.TrimSpace(group), consumer: strings.TrimSpace(consumer), now: time.Now, unresolved: map[string]struct{}{}}
	for _, option := range options {
		if option != nil {
			option(c)
		}
	}
	if c.now == nil {
		return nil, errors.New("Content Post consumer clock required")
	}
	return c, nil
}
func (c *ContentPostLifecycleConsumer) ProcessOnce(ctx context.Context) (processed int, scanErr error) {
	if c == nil || c.transport == nil || c.handler == nil {
		return 0, errors.New("Content Post lifecycle consumer is not configured")
	}
	// 同一实例只执行一个扫描；健康读取不持有此执行锁。
	c.scanMu.Lock()
	defer c.scanMu.Unlock()
	defer func() {
		c.mu.Lock()
		defer c.mu.Unlock()
		if scanErr != nil {
			c.scanError = postDigest(scanErr.Error())
			return
		}
		c.scanError = ""
		c.lastSuccess = c.now()
	}()
	c.mu.RLock()
	stopped := c.stopped
	c.mu.RUnlock()
	if stopped {
		return 0, errors.New("Content Post consumer stopped")
	}
	if err := ctx.Err(); err != nil {
		return 0, err
	}
	if err := c.transport.EnsureDurableConsumerGroup(ctx, contentPostLifecycleStream, c.group, "0"); err != nil {
		return 0, err
	}
	pending, _, err := c.transport.ReclaimDurable(ctx, contentPostLifecycleStream, c.group, c.consumer, 30*time.Second, "0-0", 50)
	if err != nil {
		return 0, err
	}
	c.rememberDeliveries(pending)
	fresh, err := c.transport.ReadDurable(ctx, messaging.StreamReadRequest{Stream: contentPostLifecycleStream, Group: c.group, Consumer: c.consumer, Count: 50, Block: 100 * time.Millisecond})
	if err != nil {
		return 0, err
	}
	c.rememberDeliveries(fresh)
	seen := map[string]bool{}
	for _, delivery := range append(pending, fresh...) {
		if err := ctx.Err(); err != nil {
			return processed, err
		}
		if delivery.Stream != contentPostLifecycleStream || strings.TrimSpace(delivery.ID) == "" {
			return processed, errors.New("Content Post lifecycle delivery identity mismatch")
		}
		if seen[delivery.ID] {
			continue
		}
		seen[delivery.ID] = true
		// 不复制UserProfile consumer的invalid->DLQ->ACK行为：这里未证明的事实仍pending。
		if err := c.handler.ApplyContentPostDelivery(ctx, delivery); err != nil {
			return processed, err
		}
		if err := c.transport.AckDurable(ctx, contentPostLifecycleStream, c.group, delivery.ID); err != nil {
			return processed, err
		}
		c.mu.Lock()
		delete(c.unresolved, postDigest([]string{delivery.Stream, delivery.ID}))
		c.mu.Unlock()
		processed++
	}
	return processed, ctx.Err()
}

// 已交付的整批先登记，包含因前一条失败尚未处理的消息。仅同delivery处理和ACK
// 均成功才移除；空读、另一条成功、pending数量变化均不是终结证据。
func (c *ContentPostLifecycleConsumer) rememberDeliveries(deliveries []messaging.StreamDelivery) {
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, delivery := range deliveries {
		key := postDigest([]string{delivery.Stream, delivery.ID})
		c.unresolved[key] = struct{}{}
	}
}

// Healthy 仅证明本实例consumer execution health，不证明未交付backlog或ES可查询时效。
// 阈值由composition沿用同服务consumer约定传入，不在对象内补默认容差。
func (c *ContentPostLifecycleConsumer) Healthy(maxStaleness time.Duration) error {
	if c == nil || maxStaleness <= 0 {
		return errors.New("Content Post consumer health requires a positive scan bound")
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.stopped {
		return errors.New("Content Post consumer stopped")
	}
	if c.scanError != "" {
		return fmt.Errorf("Content Post consumer scan failed (digest=%s)", c.scanError)
	}
	if len(c.unresolved) > 0 {
		return fmt.Errorf("Content Post consumer has %d unresolved deliveries", len(c.unresolved))
	}
	if c.lastSuccess.IsZero() {
		return errors.New("Content Post consumer has not completed a scan")
	}
	if age := c.now().Sub(c.lastSuccess); age < 0 || age > maxStaleness {
		return errors.New("Content Post consumer scan is stale")
	}
	return nil
}

// Run沿用本服务250ms轮询；停止不可由后继空扫描重新声明健康。
func (c *ContentPostLifecycleConsumer) Run(ctx context.Context, logger *slog.Logger) {
	defer func() { c.mu.Lock(); c.stopped = true; c.mu.Unlock() }()
	if logger == nil {
		logger = slog.Default()
	}
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			logger.ErrorContext(ctx, "Content Post consumer execution failed; delivery remains pending", "errorDigest", postDigest(err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
