// Package outboxrelay 提供对象专属 relay 共用的运行与健康监督，不承载业务事实或存储访问。
package outboxrelay

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"
)

const defaultScanInterval = 250 * time.Millisecond

// Supervisor 记录后台扫描的最近成功与失败，用于 readiness 与 staleness 检查。
// 对象自己的 relay 仍负责其类型化 Reader、Publisher 与 checkpoint 端口。
type Supervisor struct {
	name string

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewSupervisor(name string) *Supervisor {
	return &Supervisor{name: strings.TrimSpace(name)}
}

// Run 在 context 结束前重复执行一次持久 outbox 扫描。失败不标记成功，
// 因而下一轮会从最后已保存的 checkpoint 继续重放。
func (s *Supervisor) Run(
	ctx context.Context,
	interval time.Duration,
	drain func(context.Context) (int, error),
) error {
	if s == nil || drain == nil {
		return fmt.Errorf("outbox relay supervisor is not configured")
	}
	if interval <= 0 {
		interval = defaultScanInterval
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := drain(ctx); err != nil {
			s.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
				continue
			}
		}
		s.recordSuccess()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Healthy 只观察后台扫描状态，绝不在 readiness 路径触发投递。
func (s *Supervisor) Healthy(maxStaleness time.Duration) error {
	if s == nil {
		return fmt.Errorf("outbox relay supervisor is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}

	s.mu.RLock()
	defer s.mu.RUnlock()
	name := s.name
	if name == "" {
		name = "outbox"
	}
	if s.lastSuccess.IsZero() {
		return fmt.Errorf("%s outbox relay has not completed a scan", name)
	}
	if s.lastFailure != nil {
		return fmt.Errorf("%s outbox relay last failure: %w", name, s.lastFailure)
	}
	if age := time.Since(s.lastSuccess); age > maxStaleness {
		return fmt.Errorf(
			"%s outbox relay heartbeat is stale: %s",
			name,
			age.Round(time.Millisecond),
		)
	}
	return nil
}

func (s *Supervisor) recordSuccess() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastSuccess = time.Now().UTC()
	s.lastFailure = nil
}

func (s *Supervisor) recordFailure(err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastFailure = err
}
