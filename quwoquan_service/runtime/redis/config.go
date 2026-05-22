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

	DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	ReadTimeoutMs  int `yaml:"read_timeout_ms"`
	WriteTimeoutMs int `yaml:"write_timeout_ms"`
}

// PrefixRoute maps a key prefix to a scene name.
// The Router uses longest-prefix matching to determine routing.
type PrefixRoute struct {
	Prefix string `yaml:"prefix"`
	Scene  string `yaml:"scene"`
}

// DefaultRouterConfig returns a config suitable for local development
// (all scenes use in-memory implementation).
// Scene names and prefix routes are sourced from redis_keyspace.yaml via codegen.
func DefaultRouterConfig() RouterConfig {
	scenes := make(map[string]SceneConfig, len(GeneratedSceneNames()))
	for _, name := range GeneratedSceneNames() {
		scenes[name] = SceneConfig{Mode: "memory"}
	}
	return RouterConfig{
		Scenes:       scenes,
		PrefixRoutes: GeneratedPrefixRoutes(),
		DefaultScene: GeneratedDefaultScene,
	}
}
