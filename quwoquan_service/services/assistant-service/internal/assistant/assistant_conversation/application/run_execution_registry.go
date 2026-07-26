package application

import "sync"

// runExecutionRegistry 只负责单实例 single-flight；跨实例排他由 Redis lease 承担。
type runExecutionRegistry struct {
	mu      sync.Mutex
	running map[string]struct{}
}

func newRunExecutionRegistry() *runExecutionRegistry {
	return &runExecutionRegistry{running: map[string]struct{}{}}
}

func (registry *runExecutionRegistry) start(runID string, execute func()) bool {
	registry.mu.Lock()
	if _, exists := registry.running[runID]; exists {
		registry.mu.Unlock()
		return false
	}
	registry.running[runID] = struct{}{}
	registry.mu.Unlock()
	go func() {
		defer func() {
			registry.mu.Lock()
			delete(registry.running, runID)
			registry.mu.Unlock()
		}()
		execute()
	}()
	return true
}
