package bootstrap

import (
	"quwoquan_service/runtime/servicekit"
	postruntimeconfig "quwoquan_service/services/content-service/internal/content/post/infrastructure/runtimeconfig"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
)

// accountSecurityReadScope 是 content 对账号安全 authority 的最小服务间授权
// 范围：只读账号状态与 authEpoch，不含任何写权限。
const accountSecurityReadScope = "user.account.security.read"

// redisSceneCfg 是骨架 scene 声明的本包别名：领域校验与装配辅助函数按同一
// 结构读取一个 Redis scene 的物理组网。
type redisSceneCfg = servicekit.RedisSceneConfig

type feedRuntimeConfig struct {
	ActiveSupplyCacheTTLMS            int   `yaml:"active_supply_cache_ttl_ms"`
	ActiveSupplyCacheJitterMS         int   `yaml:"active_supply_cache_jitter_ms"`
	MaxInflight                       int   `yaml:"max_inflight"`
	MaximumRecallSources              int   `yaml:"maximum_recall_sources"`
	MaximumUnterminatedCallsPerSource int   `yaml:"maximum_unterminated_calls_per_source"`
	DeliveryPageQuotaShardCount       int   `yaml:"delivery_page_quota_shard_count"`
	DeliveryPageMaximumLiveRecords    int   `yaml:"delivery_page_maximum_live_records_per_shard"`
	DeliveryPageMaximumLiveBytes      int64 `yaml:"delivery_page_maximum_live_bytes_per_shard"`
}

// config 是 content-service 的声明式运行配置：通用段内嵌 servicekit.BaseConfig，
// env 覆盖键全部由 tag 派生（服务前缀 CONTENT）。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	// Mongo 不用 servicekit.MongoConfig：content 的快照多一段 collection，
	// 而声明即装配只识别 URI/Database 两字段的那个类型。连接仍走
	// asm.Mongo(...)，健康检查与断连清理由骨架注册。
	Mongo struct {
		URI        string `yaml:"uri" env:"MONGO_URI" required:"true"`
		Database   string `yaml:"database" env:"MONGO_DATABASE" required:"true"`
		Collection string `yaml:"collection" required:"true"`
	} `yaml:"mongo"`

	// Postgres 承载举报事实存储。领域实现消费 database/sql 的 *sql.DB，
	// 而 servicekit.PostgresConfig 装配的是 pgxpool，因此这里保持自有声明。
	Postgres struct {
		ReportDSN string `yaml:"report_dsn" env:"POSTGRES_REPORT_DSN" required:"true"`
	} `yaml:"postgres"`

	IPLocation struct {
		Provider         string `yaml:"provider" env:"PROVIDER"`
		IPv4DatabasePath string `yaml:"ipv4_database_path" env:"IPV4_DATABASE_PATH"`
		IPv6DatabasePath string `yaml:"ipv6_database_path" env:"IPV6_DATABASE_PATH"`
		DataVersion      string `yaml:"data_version" env:"DATA_VERSION"`
	} `yaml:"ip_location" envPrefix:"IP_LOCATION"`

	CommentRateLimit struct {
		BurstWindowSeconds int   `yaml:"burst_window_seconds"`
		BurstMax           int64 `yaml:"burst_max"`
		DailyWindowSeconds int   `yaml:"daily_window_seconds"`
		DailyMax           int64 `yaml:"daily_max"`
	} `yaml:"comment_rate_limit"`

	// Redis scenes:
	//   rec      — 推荐热路径（会话信号、已曝光、负反馈）
	//   general  — 实体缓存、durable 事实流、限流
	//   realtime — 实时推送流，与 realtime-gateway 同 db
	Redis struct {
		Rec      redisSceneCfg `yaml:"rec" envPrefix:"REC"`
		General  redisSceneCfg `yaml:"general" envPrefix:"GENERAL"`
		Realtime redisSceneCfg `yaml:"realtime" envPrefix:"REALTIME"`
	} `yaml:"redis" envPrefix:"REDIS"`

	RecModelService postruntimeconfig.RecommendationModelConfig `yaml:"rec_model_service" envPrefix:"REC_MODEL_SERVICE"`

	TagService struct {
		URL       string `yaml:"url" env:"URL"`
		TimeoutMs int    `yaml:"timeout_ms" env:"TIMEOUT_MS"`
	} `yaml:"tag_service" envPrefix:"TAG_SERVICE"`

	// CircleService 是共同经历回流引用（post.gatheringRef）的 Participation
	// 校验上游；缺失时携带 gatheringRef 的发布 fail-closed。
	CircleService struct {
		URL       string `yaml:"url"`
		TimeoutMs int    `yaml:"timeout_ms"`
	} `yaml:"circle_service"`

	Embedding struct {
		// Enabled 开启 embedding 写入管线（PostPublished → posts.embedding）。
		Enabled bool `yaml:"enabled"`
		// VectorRecallEnabled 开启向量召回读通道（S0 flag-off；S1 内容池规模
		// 阈值达标后开启——阶段门触发条件见推荐商用二期 Stage Gates）。
		VectorRecallEnabled bool `yaml:"vector_recall_enabled"`
	} `yaml:"embedding"`

	Feed feedRuntimeConfig `yaml:"feed"`

	OSS struct {
		// Endpoint/AccessKeyID/AccessKeySecret 只经 runtime.object.storage
		// binding 轨解析（generated descriptor 声明的
		// CONTENT_OSS_ENDPOINT / CONTENT_OSS_ACCESS_KEY_ID / _SECRET），
		// 因此这里不再声明第二条读取轨。快照仍保留 endpoint 键位。
		Endpoint string `yaml:"endpoint"`
		Bucket   string `yaml:"bucket" env:"OSS_BUCKET" required:"true"`
		Region   string `yaml:"region" env:"OSS_REGION" required:"true"`
		// 交付/上传基址与 CDN 签名 key 在快照里可为空（本地 MinIO 直连），
		// 强度判定归媒体装配，这里不加 required 以免收紧存量环境的启动条件。
		MediaDeliveryBaseURL string `yaml:"media_delivery_base_url" env:"MEDIA_DELIVERY_BASE_URL"`
		MediaUploadBaseURL   string `yaml:"media_upload" env:"MEDIA_UPLOAD_BASE_URL"`
		CDNSignKey           string `yaml:"cdn_sign_key" env:"CDN_SIGN_KEY"`
		PresignTTLMin        int    `yaml:"presign_ttl_minutes"`
		CDNTTLMin            int    `yaml:"cdn_ttl_minutes"`
		UseSSL               bool   `yaml:"use_ssl"`
	} `yaml:"oss"`

	// MediaProcessing 配置强制启用的进程内 Worker；它是 media outbox
	// 唯一生产 consumer。
	MediaProcessing struct {
		IntervalMs          int    `yaml:"interval_ms"`
		FFmpegPath          string `yaml:"ffmpeg_path"`
		FFprobePath         string `yaml:"ffprobe_path"`
		HLSCMAFEnabled      bool   `yaml:"hls_cmaf_enabled"`
		WorkDir             string `yaml:"work_dir"`
		JobTimeoutMs        int    `yaml:"job_timeout_ms"`
		MinWorkDirFreeBytes int64  `yaml:"min_work_dir_free_bytes"`
	} `yaml:"media_processing"`

	// ES is the write side of the unified search index (content.search_index_worker).
	// Endpoints/credentials are injected per-env via the shared SEARCH_ES_* env so
	// content-service and search-service target the same cluster/index. Disabled by
	// default; when off the search-index projector is a no-op and the write path is
	// unaffected.
	ES searchindex.ESConfig `yaml:"es"`
}
