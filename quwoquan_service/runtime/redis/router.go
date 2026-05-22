package redis

import (
	"context"
	"fmt"
	"log"
	"sort"
	"strings"
)

// Router provides scene-based and prefix-based Redis routing.
// Upper layers call Scene(name) for explicit scene access or
// ForKey(key) for automatic prefix-based routing.
type Router struct {
	scenes       map[string]Client
	prefixRoutes []PrefixRoute // sorted by prefix length descending (longest first)
	defaultScene string
}

// MustNewRouter creates a Router from config; panics on error.
func MustNewRouter(cfg RouterConfig) *Router {
	r, err := NewRouter(cfg)
	if err != nil {
		panic(fmt.Sprintf("redis.MustNewRouter: %v", err))
	}
	return r
}

// NewRouter creates a Router from config.
func NewRouter(cfg RouterConfig) (*Router, error) {
	if len(cfg.Scenes) == 0 {
		return nil, fmt.Errorf("redis: at least one scene must be configured")
	}

	scenes := make(map[string]Client, len(cfg.Scenes))
	for name, scfg := range cfg.Scenes {
		client, err := newSceneClient(scfg)
		if err != nil {
			return nil, fmt.Errorf("redis: scene %q: %w", name, err)
		}
		log.Printf("redis: scene %q initialized (mode=%s)", name, scfg.Mode)
		scenes[name] = client
	}

	routes := make([]PrefixRoute, len(cfg.PrefixRoutes))
	copy(routes, cfg.PrefixRoutes)
	sort.Slice(routes, func(i, j int) bool {
		return len(routes[i].Prefix) > len(routes[j].Prefix)
	})

	for _, pr := range routes {
		if _, ok := scenes[pr.Scene]; !ok {
			return nil, fmt.Errorf("redis: prefix route %q references unknown scene %q", pr.Prefix, pr.Scene)
		}
	}

	def := cfg.DefaultScene
	if def == "" {
		def = "general"
	}
	if _, ok := scenes[def]; !ok {
		return nil, fmt.Errorf("redis: default scene %q not found", def)
	}

	return &Router{
		scenes:       scenes,
		prefixRoutes: routes,
		defaultScene: def,
	}, nil
}

// Scene returns the Client for a named scene.
func (r *Router) Scene(name string) Client {
	c, ok := r.scenes[name]
	if !ok {
		panic(fmt.Sprintf("redis: unknown scene %q", name))
	}
	return c
}

// ForKey returns the Client for a key based on prefix routing rules.
// Falls back to the default scene if no prefix matches.
func (r *Router) ForKey(key string) Client {
	for _, pr := range r.prefixRoutes {
		if strings.HasPrefix(key, pr.Prefix) {
			return r.scenes[pr.Scene]
		}
	}
	return r.scenes[r.defaultScene]
}

// Close shuts down all scene clients.
func (r *Router) Close() error {
	var firstErr error
	for name, c := range r.scenes {
		if err := c.Close(); err != nil && firstErr == nil {
			firstErr = fmt.Errorf("redis: close scene %q: %w", name, err)
		}
	}
	return firstErr
}

// Scenes returns all scene names (for metrics/health checks).
func (r *Router) Scenes() []string {
	names := make([]string, 0, len(r.scenes))
	for n := range r.scenes {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}

// PingAll pings every scene and returns the first error encountered.
func (r *Router) PingAll(ctx context.Context) error {
	for _, name := range r.Scenes() {
		if err := r.scenes[name].Ping(ctx); err != nil {
			return fmt.Errorf("redis: ping scene %q: %w", name, err)
		}
	}
	return nil
}
