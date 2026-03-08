package redis

// RouterConfig holds the complete Redis configuration for all scenes.
type RouterConfig struct {
	Scenes       map[string]SceneConfig `yaml:"scenes"`
	PrefixRoutes []PrefixRoute          `yaml:"prefix_routes"`
	DefaultScene string                 `yaml:"default_scene"`
}

// SceneConfig configures a single Redis scene (e.g. rec, general, realtime).
type SceneConfig struct {
	Mode     string   `yaml:"mode"` // "standalone", "cluster", "memory"
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`

	PoolSize     int `yaml:"pool_size"`
	MinIdleConns int `yaml:"min_idle_conns"`
}

// PrefixRoute maps a key prefix to a scene name.
// The Router uses longest-prefix matching to determine routing.
type PrefixRoute struct {
	Prefix string `yaml:"prefix"`
	Scene  string `yaml:"scene"`
}

// DefaultRouterConfig returns a config suitable for local development
// (all scenes use in-memory implementation).
func DefaultRouterConfig() RouterConfig {
	return RouterConfig{
		Scenes: map[string]SceneConfig{
			"rec":      {Mode: "memory"},
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		PrefixRoutes: []PrefixRoute{
			{Prefix: "rec:", Scene: "rec"},
			{Prefix: "cache:", Scene: "general"},
			{Prefix: "counter:", Scene: "general"},
			{Prefix: "reaction:", Scene: "general"},
			{Prefix: "rt:", Scene: "realtime"},
			{Prefix: "seq:", Scene: "realtime"},
			{Prefix: "presence:", Scene: "realtime"},
			{Prefix: "dedup:", Scene: "realtime"},
			{Prefix: "transport:", Scene: "realtime"},
		},
		DefaultScene: "general",
	}
}
