package main

import "quwoquan_service/services/content-service/internal/infrastructure/searchindex"

// redisSceneCfg holds configuration for a single Redis deployment (one logical scene).
type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`  // "standalone" (default) | "cluster"
	Addr     string   `yaml:"addr"`  // standalone: host:port
	Addrs    []string `yaml:"addrs"` // cluster: [host:port, ...]
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`  // cluster mode ignores this
	TLS      bool     `yaml:"tls"` // set true for Alibaba Cloud / VeCache public endpoints
	Pool     struct {
		Size           int `yaml:"size"`     // 0 = auto
		MinIdle        int `yaml:"min_idle"` // 0 = auto
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Mongo struct {
		URI        string `yaml:"uri"`
		Database   string `yaml:"database"`
		Collection string `yaml:"collection"`
	} `yaml:"mongo"`
	Postgres struct {
		ReportDSN string `yaml:"report_dsn"`
	} `yaml:"postgres"`

	IPLocation struct {
		Provider         string `yaml:"provider"`
		IPv4DatabasePath string `yaml:"ipv4_database_path"`
		IPv6DatabasePath string `yaml:"ipv6_database_path"`
		DataVersion      string `yaml:"data_version"`
	} `yaml:"ip_location"`

	CommentRateLimit struct {
		BurstWindowSeconds int   `yaml:"burst_window_seconds"`
		BurstMax           int64 `yaml:"burst_max"`
		DailyWindowSeconds int   `yaml:"daily_window_seconds"`
		DailyMax           int64 `yaml:"daily_max"`
	} `yaml:"comment_rate_limit"`

	// Redis scenes:
	//   rec     — recommendation hot path (session signals, exposed, negative)
	//   general — entity cache, assistant context, rate limiting (reserved)
	Redis struct {
		Rec      redisSceneCfg `yaml:"rec"`
		General  redisSceneCfg `yaml:"general"`
		Realtime redisSceneCfg `yaml:"realtime"`
	} `yaml:"redis"`

	RecModelService struct {
		URL       string `yaml:"url"`
		TimeoutMs int    `yaml:"timeout_ms"`
		Enabled   bool   `yaml:"enabled"`
	} `yaml:"rec_model_service"`

	Embedding struct {
		Endpoint string `yaml:"endpoint"`
		APIKey   string `yaml:"api_key"`
		Model    string `yaml:"model"`
		// Enabled 开启 embedding 写入管线（PostPublished → posts.embedding）。
		Enabled bool `yaml:"enabled"`
		// VectorRecallEnabled 开启向量召回读通道（S0 flag-off；S1 内容池规模
		// 阈值达标后开启——阶段门触发条件见推荐商用二期 Stage Gates）。
		VectorRecallEnabled bool `yaml:"vector_recall_enabled"`
	} `yaml:"embedding"`

	OSS struct {
		Endpoint        string `yaml:"endpoint"`
		Bucket          string `yaml:"bucket"`
		Region          string `yaml:"region"`
		AccessKeyID     string `yaml:"access_key_id"`
		AccessKeySecret string `yaml:"access_key_secret"`
		CDNDomain       string `yaml:"cdn_domain"`
		CDNSignKey      string `yaml:"cdn_sign_key"`
		PresignTTLMin   int    `yaml:"presign_ttl_minutes"`
		CDNTTLMin       int    `yaml:"cdn_ttl_minutes"`
		UseSSL          bool   `yaml:"use_ssl"`
	} `yaml:"oss"`

	// MediaProcessing 配置强制启用的进程内 Worker；它是 media outbox
	// 唯一生产 consumer。
	MediaProcessing struct {
		IntervalMs   int    `yaml:"interval_ms"`
		FFmpegPath   string `yaml:"ffmpeg_path"`
		FFprobePath  string `yaml:"ffprobe_path"`
		WorkDir      string `yaml:"work_dir"`
		JobTimeoutMs int    `yaml:"job_timeout_ms"`
	} `yaml:"media_processing"`

	// ES is the write side of the unified search index (content.search_index_worker).
	// Endpoints/credentials are injected per-env via the shared SEARCH_ES_* env so
	// content-service and search-service target the same cluster/index. Disabled by
	// default; when off the search-index projector is a no-op and the write path is
	// unaffected.
	ES searchindex.ESConfig `yaml:"es"`
}
