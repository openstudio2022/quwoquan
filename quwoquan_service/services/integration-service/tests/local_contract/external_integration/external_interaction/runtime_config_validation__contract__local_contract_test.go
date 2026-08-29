package local_contract

import (
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

// integrationEnvPrefix 是服务名派生的 env 键前缀，测试与启动共用同一来源。
var integrationEnvPrefix = servicekit.DefaultEnvPrefix("integration-service")

func applyIntegrationEnvOverrides(t *testing.T) integrationconfig.Config {
	t.Helper()
	cfg := integrationconfig.Config{}
	if err := servicekit.ApplyEnvOverrides(integrationEnvPrefix, &cfg); err != nil {
		t.Fatalf("apply env overrides: %v", err)
	}
	return cfg
}

// validatableExternalInteractionConfig 只填满 Validate 在 SMS provider 之前
// 就会拦下的必填项，让每个子用例只改一个字段，失败原因唯一可归因。
func validatableExternalInteractionConfig() integrationconfig.Config {
	cfg := integrationconfig.Config{}
	cfg.Environment = "gamma"
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "quwoquan_integration"
	cfg.UserAccountSecurityAuthority.BaseURL = "http://user-service:18081"
	cfg.UserAccountSecurityAuthority.TimeoutMs = 300
	return cfg
}

// 未解析的 `${...}` 占位符与空串同义：渲染失败必须在启动校验就暴露，
// 不能带着字面量占位符去连 Mongo。
func TestValidateRejectsUnresolvedMongoPlaceholders(t *testing.T) {
	for _, testCase := range []struct {
		name    string
		mutate  func(*integrationconfig.Config)
		wantErr string
	}{
		{
			name:    "uri unset",
			mutate:  func(cfg *integrationconfig.Config) { cfg.MongoDB.URI = "" },
			wantErr: "mongodb.uri is required",
		},
		{
			name:    "uri placeholder",
			mutate:  func(cfg *integrationconfig.Config) { cfg.MongoDB.URI = "${INTEGRATION_MONGO_URI}" },
			wantErr: "mongodb.uri is required",
		},
		{
			name:    "database unset",
			mutate:  func(cfg *integrationconfig.Config) { cfg.MongoDB.Database = "" },
			wantErr: "mongodb.database is required",
		},
		{
			name: "database placeholder",
			mutate: func(cfg *integrationconfig.Config) {
				cfg.MongoDB.Database = "${INTEGRATION_MONGO_DATABASE}"
			},
			wantErr: "mongodb.database is required",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			cfg := validatableExternalInteractionConfig()
			testCase.mutate(&cfg)
			err := integrationconfig.Validate(cfg)
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}

// SMS provider 一旦 enabled，Provider/Endpoint/Token/Timeout 就是投递的全部凭据；
// 缺任何一项都必须在启动期阻断，否则运行期会把验证码发到未定义目标。
func TestValidateRejectsIncompleteEnabledSMSProviderMaterial(t *testing.T) {
	for _, testCase := range []struct {
		name        string
		environment string
		provider    integrationconfig.ExternalProviderConfig
		wantErr     string
	}{
		{
			name:     "provider name missing",
			provider: integrationconfig.ExternalProviderConfig{Enabled: true},
			wantErr: "external provider name is required for enabled operation " +
				reliabletask.ExternalInteractionOperationSmsOTP,
		},
		{
			name: "mock provider forbidden",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.mock_capture",
			},
			wantErr: "cannot use mock provider",
		},
		{
			name:        "local capture forbidden in prod",
			environment: "prod",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.local_capture",
			},
			wantErr: "SMS local_capture is forbidden in prod",
		},
		{
			name: "local capture requires pinned CA",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.local_capture",
			},
			wantErr: "SMS local_capture CA file is required",
		},
		{
			name: "endpoint missing",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.aliyun",
			},
			wantErr: "external provider endpoint is required",
		},
		{
			name: "token missing",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.aliyun",
				Endpoint: "https://sms.example.test/v1/send",
			},
			wantErr: "external provider token is required",
		},
		{
			name: "timeout missing",
			provider: integrationconfig.ExternalProviderConfig{
				Enabled:  true,
				Provider: "ext.sms.aliyun",
				Endpoint: "https://sms.example.test/v1/send",
				Token:    "provider-token",
			},
			wantErr: "external provider timeout is required",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			cfg := validatableExternalInteractionConfig()
			if testCase.environment != "" {
				cfg.Environment = testCase.environment
			}
			cfg.Integration.ExternalInteraction.SMS = testCase.provider
			err := integrationconfig.Validate(cfg)
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}

// disabled 的 SMS 能力不带任何材料也必须准出：能力被 metadata 关闭时，
// 启动校验不能反过来要求它提供凭据。
func TestValidateAcceptsDisabledSMSProviderWithoutMaterial(t *testing.T) {
	cfg := validatableExternalInteractionConfig()
	cfg.Integration.ExternalInteraction.SMS = integrationconfig.ExternalProviderConfig{}
	if err := integrationconfig.Validate(cfg); err != nil {
		t.Fatalf("disabled SMS capability must stay valid: %v", err)
	}

	cfg.Integration.ExternalInteraction.SMS = integrationconfig.ExternalProviderConfig{
		Enabled:   true,
		Provider:  "ext.sms.aliyun",
		Endpoint:  "https://sms.example.test/v1/send",
		Token:     "provider-token",
		TimeoutMs: 10000,
	}
	if err := integrationconfig.Validate(cfg); err != nil {
		t.Fatalf("complete SMS material must stay valid: %v", err)
	}
}

// Push 协议替身只在非生产成立，且 endpoint 必须是 https 绝对地址；
// 真实模式则必须给齐 APNs/FCM 凭据并且密钥文件真实可读，
// 否则服务会在首次推送时才发现凭据缺失。
func TestValidateEnforcesPushDeliveryMaterialPerMode(t *testing.T) {
	secretsDir := t.TempDir()
	apnsKey := filepath.Join(secretsDir, "AuthKey.p8")
	fcmAccount := filepath.Join(secretsDir, "fcm.json")
	writeRuntimeConfigFile(t, apnsKey, "-----BEGIN PRIVATE KEY-----\n")
	writeRuntimeConfigFile(t, fcmAccount, "{\"type\":\"service_account\"}\n")
	emptyFCM := filepath.Join(secretsDir, "empty-fcm.json")
	writeRuntimeConfigFile(t, emptyFCM, "")

	realPush := func() integrationconfig.PushDeliveryProviderConfig {
		push := integrationconfig.PushDeliveryProviderConfig{
			Enabled:            true,
			Mode:               "real",
			TimeoutMs:          5000,
			UserServiceBaseURL: "http://user-service:18081",
		}
		push.APNs.Environment = "sandbox"
		push.APNs.KeyFile = apnsKey
		push.APNs.KeyID = "test-key-id"
		push.APNs.TeamID = "test-team-id"
		push.APNs.Topic = "com.example.app.voip"
		push.FCM.ServiceAccountFile = fcmAccount
		push.FCM.ProjectID = "test-project"
		return push
	}

	for _, testCase := range []struct {
		name        string
		environment string
		push        func() integrationconfig.PushDeliveryProviderConfig
		wantErr     string
	}{
		{
			name: "substitute endpoint must be https",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				return integrationconfig.PushDeliveryProviderConfig{
					Enabled:   true,
					Mode:      "protocol_substitute",
					TimeoutMs: 5000,
					Endpoint:  "http://provider-protocol-substitute:18089/push/send",
				}
			},
			wantErr: "protocol_substitute endpoint is invalid",
		},
		{
			name: "unknown mode is rejected",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				return integrationconfig.PushDeliveryProviderConfig{
					Enabled:   true,
					Mode:      "local_stub",
					TimeoutMs: 5000,
				}
			},
			wantErr: "integration push mode must be real/remote",
		},
		{
			name: "real mode requires user service base url",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				push := realPush()
				push.UserServiceBaseURL = ""
				return push
			},
			wantErr: "integration push user_service_base_url is required",
		},
		{
			name: "apns environment must be sandbox or production",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				push := realPush()
				push.APNs.Environment = "staging"
				return push
			},
			wantErr: "apns.environment must be sandbox or production",
		},
		{
			name: "fcm credential file must be non-empty",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				push := realPush()
				push.FCM.ServiceAccountFile = emptyFCM
				return push
			},
			wantErr: "FCM service-account secret file must be a non-empty regular file",
		},
		{
			name: "fcm credential file must exist",
			push: func() integrationconfig.PushDeliveryProviderConfig {
				push := realPush()
				push.FCM.ServiceAccountFile = filepath.Join(secretsDir, "absent-fcm.json")
				return push
			},
			wantErr: "FCM service-account secret file is required",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			cfg := validatableExternalInteractionConfig()
			if testCase.environment != "" {
				cfg.Environment = testCase.environment
			}
			cfg.Integration.ExternalInteraction.Push = testCase.push()
			err := integrationconfig.Validate(cfg)
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}

	cfg := validatableExternalInteractionConfig()
	cfg.Integration.ExternalInteraction.Push = realPush()
	if err := integrationconfig.Validate(cfg); err != nil {
		t.Fatalf("complete real push material must stay valid: %v", err)
	}

	substitute := validatableExternalInteractionConfig()
	substitute.Integration.ExternalInteraction.Push = integrationconfig.PushDeliveryProviderConfig{
		Enabled:   true,
		Mode:      "protocol_substitute",
		TimeoutMs: 5000,
		Endpoint:  "https://provider-protocol-substitute:18089/push/send",
	}
	if err := integrationconfig.Validate(substitute); err != nil {
		t.Fatalf("gamma protocol substitute must stay valid: %v", err)
	}
}

// 结果中继必须有真实 Redis 才能保证回执不丢：只有 alpha 允许内存模式，
// 其余环境缺 addr/addrs 或写了非法 mode 都必须 fail closed。
func TestValidateResultRelayRedisRequiresDurableTransportOutsideAlpha(t *testing.T) {
	for _, testCase := range []struct {
		name        string
		environment string
		redis       integrationconfig.RedisSceneConfig
		wantErr     string
	}{
		{
			name:        "alpha memory is allowed",
			environment: "alpha",
			redis:       integrationconfig.RedisSceneConfig{Mode: "memory"},
		},
		{
			name:        "standalone addr present",
			environment: "gamma",
			redis:       integrationconfig.RedisSceneConfig{Mode: "standalone", Addr: "redis:6379"},
		},
		{
			name:        "cluster addrs present",
			environment: "prod",
			redis: integrationconfig.RedisSceneConfig{
				Mode:  "cluster",
				Addrs: []string{"redis-0:6379", "redis-1:6379"},
			},
		},
		{
			name:        "standalone without addr",
			environment: "gamma",
			redis:       integrationconfig.RedisSceneConfig{Mode: "standalone"},
			wantErr:     "redis.general.addr is required for external result relay when APP_ENV=gamma",
		},
		{
			name:        "cluster without addrs",
			environment: "prod",
			redis:       integrationconfig.RedisSceneConfig{Mode: "cluster"},
			wantErr:     "redis.general.addrs is required for external result relay when APP_ENV=prod",
		},
		{
			name:        "memory outside alpha",
			environment: "beta",
			redis:       integrationconfig.RedisSceneConfig{Mode: "memory"},
			wantErr:     "redis.general.mode must be memory in alpha or standalone/cluster",
		},
		{
			name:        "unknown mode",
			environment: "gamma",
			redis:       integrationconfig.RedisSceneConfig{Mode: "sentinel"},
			wantErr:     "redis.general.mode must be memory in alpha or standalone/cluster",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			err := integrationconfig.ValidateResultRelayRedis(testCase.environment, testCase.redis)
			if testCase.wantErr == "" {
				if err != nil {
					t.Fatalf("want valid relay transport, got %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}

// 环境覆盖是渲染后配置的唯一合法改写入口：Mongo 定位、监听地址、默认坐标
// 都要被真正写回 Config，且键集单轨——无前缀的共享键不再参与覆盖。
func TestApplyEnvOverridesRewritesCanonicalRuntimeTargets(t *testing.T) {
	t.Setenv("MONGO_URI", "mongodb://shared:27017")
	t.Setenv("MONGO_DATABASE", "shared_db")
	t.Setenv("INTEGRATION_MONGO_URI", "mongodb://integration:27017")
	t.Setenv("INTEGRATION_MONGO_DATABASE", "integration_db")
	t.Setenv("INTEGRATION_SERVICE_ADDR", ":19086")
	t.Setenv("INTEGRATION_LOCATION_DEFAULT_LATITUDE", "31.2304")
	t.Setenv("INTEGRATION_LOCATION_DEFAULT_LONGITUDE", "121.4737")

	cfg := applyIntegrationEnvOverrides(t)
	if cfg.MongoDB.URI != "mongodb://integration:27017" ||
		cfg.MongoDB.Database != "integration_db" {
		t.Fatalf("service scoped Mongo override must win: %#v", cfg.MongoDB)
	}
	if cfg.Service.HTTP.Addr != ":19086" {
		t.Fatalf("listen addr override drift: %q", cfg.Service.HTTP.Addr)
	}
	if cfg.Integration.Location.DefaultLatitude != 31.2304 ||
		cfg.Integration.Location.DefaultLongitude != 121.4737 {
		t.Fatalf("default coordinate override drift: %#v", cfg.Integration.Location)
	}
}

// 坐标覆盖是数值语义，非数值必须阻断而不是静默退回默认坐标，
// 否则附近查询会落到与运营预期无关的城市。
func TestApplyEnvOverridesRejectsNonNumericCoordinates(t *testing.T) {
	for _, key := range []string{
		"INTEGRATION_LOCATION_DEFAULT_LATITUDE",
		"INTEGRATION_LOCATION_DEFAULT_LONGITUDE",
	} {
		t.Run(key, func(t *testing.T) {
			t.Setenv(key, "not-a-number")
			cfg := integrationconfig.Config{}
			err := servicekit.ApplyEnvOverrides(integrationEnvPrefix, &cfg)
			if err == nil || !strings.Contains(err.Error(), "env "+key+" must be numeric") {
				t.Fatalf("want %s numeric guard, got %v", key, err)
			}
		})
	}
}

// Redis 场景覆盖按前缀区分 general/rec 两套连接：cluster 地址列表要去空白、
// DB 与 TLS 是强类型值，非法输入必须阻断而不是退回零值连错实例。
func TestApplyEnvOverridesMaterializesRedisScenesPerPrefix(t *testing.T) {
	t.Setenv("INTEGRATION_REDIS_GENERAL_MODE", "cluster")
	t.Setenv("INTEGRATION_REDIS_GENERAL_ADDRS", " redis-0:6379 , ,redis-1:6379 ")
	t.Setenv("INTEGRATION_REDIS_GENERAL_PASSWORD", "general-secret")
	t.Setenv("INTEGRATION_REDIS_GENERAL_DB", "3")
	t.Setenv("INTEGRATION_REDIS_GENERAL_TLS", "true")
	t.Setenv("INTEGRATION_REDIS_REC_MODE", "standalone")
	t.Setenv("INTEGRATION_REDIS_REC_ADDR", "redis-rec:6379")

	cfg := applyIntegrationEnvOverrides(t)
	if cfg.Redis.General.Mode != "cluster" ||
		strings.Join(cfg.Redis.General.Addrs, "|") != "redis-0:6379|redis-1:6379" {
		t.Fatalf("general cluster addrs drift: %#v", cfg.Redis.General)
	}
	if cfg.Redis.General.Password != "general-secret" || cfg.Redis.General.DB != 3 ||
		!cfg.Redis.General.TLS {
		t.Fatalf("general connection material drift: %#v", cfg.Redis.General)
	}
	if cfg.Redis.Rec.Mode != "standalone" || cfg.Redis.Rec.Addr != "redis-rec:6379" ||
		cfg.Redis.Rec.TLS {
		t.Fatalf("rec scene must stay independent: %#v", cfg.Redis.Rec)
	}
}

func TestApplyEnvOverridesRejectsMalformedRedisSceneValues(t *testing.T) {
	for _, testCase := range []struct {
		key     string
		value   string
		wantErr string
	}{
		{
			key:     "INTEGRATION_REDIS_GENERAL_TLS",
			value:   "yes-please",
			wantErr: "env INTEGRATION_REDIS_GENERAL_TLS: must be a boolean literal",
		},
		{
			key:     "INTEGRATION_REDIS_REC_DB",
			value:   "not-an-int",
			wantErr: "env INTEGRATION_REDIS_REC_DB must be an integer",
		},
	} {
		t.Run(testCase.key+"="+testCase.value, func(t *testing.T) {
			t.Setenv(testCase.key, testCase.value)
			cfg := integrationconfig.Config{}
			err := servicekit.ApplyEnvOverrides(integrationEnvPrefix, &cfg)
			if err == nil || !strings.Contains(err.Error(), testCase.wantErr) {
				t.Fatalf("want %q, got %v", testCase.wantErr, err)
			}
		})
	}
}

// 负数逻辑库编号在装配 scene 路由时阻断：静默取 0 会把本 scene 的读写落到
// 另一个 db。
func TestRedisSceneRouterRejectsNegativeLogicalDatabase(t *testing.T) {
	t.Setenv("INTEGRATION_REDIS_GENERAL_DB", "-1")
	cfg := applyIntegrationEnvOverrides(t)
	_, _, err := servicekit.NewRedisRouter(
		map[string]servicekit.RedisSceneConfig{"general": cfg.Redis.General},
	)
	if err == nil || !strings.Contains(err.Error(), "db must be a non-negative integer") {
		t.Fatalf("negative logical database must fail closed: %v", err)
	}
}

// APP_ENV 是四环境闭集，gamma/prod 还必须携带 CONFIG_VERSION：
// 缺任一项都不能落到「按 alpha 默认值启动」这种静默降级。
func TestLoadFailsClosedOnEnvironmentIdentity(t *testing.T) {
	configRoot := t.TempDir()
	writeRuntimeConfigFile(
		t,
		filepath.Join(configRoot, "integration-service.yaml"),
		"service:\n  http:\n    addr: :18086\n",
	)
	t.Run("unknown app env", func(t *testing.T) {
		t.Setenv("SERVICE_NAME", "")
		t.Setenv("APP_ENV", "staging")
		t.Setenv("CONFIG_ROOT", configRoot)
		if _, err := servicekit.ResolveIdentity("integration-service"); err == nil ||
			!strings.Contains(err.Error(), "APP_ENV must be one of alpha|beta|gamma|prod") {
			t.Fatalf("unknown APP_ENV must fail closed: %v", err)
		}
	})
	t.Run("gamma without config version", func(t *testing.T) {
		t.Setenv("SERVICE_NAME", "")
		t.Setenv("APP_ENV", "gamma")
		t.Setenv("CONFIG_ROOT", configRoot)
		t.Setenv("CONFIG_VERSION", "")
		if _, err := servicekit.ResolveIdentity("integration-service"); err == nil ||
			!strings.Contains(err.Error(), "CONFIG_VERSION is required when APP_ENV=gamma") {
			t.Fatalf("gamma without CONFIG_VERSION must fail closed: %v", err)
		}
	})
	t.Run("missing rendered snapshot", func(t *testing.T) {
		t.Setenv("SERVICE_NAME", "")
		t.Setenv("APP_ENV", "beta")
		t.Setenv("CONFIG_ROOT", filepath.Join(configRoot, "absent"))
		identity, err := servicekit.ResolveIdentity("integration-service")
		if err != nil {
			t.Fatalf("resolve runtime identity: %v", err)
		}
		cfg := integrationconfig.Config{}
		if _, err := servicekit.LoadYAMLConfigRaw(identity, &cfg); err == nil ||
			!strings.Contains(err.Error(), "generated runtime config") {
			t.Fatalf("absent rendered snapshot must fail closed: %v", err)
		}
	})
	t.Run("retired key inside snapshot", func(t *testing.T) {
		retiredRoot := t.TempDir()
		writeRuntimeConfigFile(
			t,
			filepath.Join(retiredRoot, "integration-service.yaml"),
			"integration:\n  external_interaction:\n    sms:\n      enabled: true\n",
		)
		t.Setenv("SERVICE_NAME", "")
		t.Setenv("APP_ENV", "beta")
		t.Setenv("CONFIG_ROOT", retiredRoot)
		identity, err := servicekit.ResolveIdentity("integration-service")
		if err != nil {
			t.Fatalf("resolve runtime identity: %v", err)
		}
		cfg := integrationconfig.Config{}
		raw, err := servicekit.LoadYAMLConfigRaw(identity, &cfg)
		if err != nil {
			t.Fatalf("load rendered snapshot: %v", err)
		}
		if err := integrationconfig.SnapshotGuard(raw); err == nil ||
			!strings.Contains(err.Error(), "generated external provider binding") {
			t.Fatalf("retired snapshot key must fail closed: %v", err)
		}
	})
}

// APP_ENV 缺省即 alpha，且 alpha 不要求 CONFIG_VERSION：本地开发入口必须
// 在零环境变量下仍然读到同一份渲染产物，而不是走第二套默认值。
func TestLoadDefaultsToAlphaWithoutConfigVersion(t *testing.T) {
	configRoot := t.TempDir()
	writeRuntimeConfigFile(
		t,
		filepath.Join(configRoot, "integration-service.yaml"),
		"mongodb:\n  uri: mongodb://mongodb:27017\n  database: quwoquan_integration\n",
	)
	t.Setenv("SERVICE_NAME", "")
	t.Setenv("APP_ENV", "")
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("CONFIG_ROOT", configRoot)

	cfg := loadIntegrationSnapshot(t)
	if cfg.Environment != "alpha" || cfg.MongoDB.Database != "quwoquan_integration" {
		t.Fatalf("alpha default snapshot drift: %#v", cfg)
	}
}

// 快照加载是唯一的渲染产物读取点：文件不可读或结构与 Config 不符都必须
// 报错，不能把半份配置合进内存后继续启动。
func TestSnapshotLoadFailsClosedOnUnreadableOrMistypedSnapshot(t *testing.T) {
	t.Setenv("SERVICE_NAME", "")
	t.Setenv("APP_ENV", "beta")
	t.Setenv("CONFIG_VERSION", "")

	t.Setenv("CONFIG_ROOT", t.TempDir())
	identity, err := servicekit.ResolveIdentity("integration-service")
	if err != nil {
		t.Fatalf("resolve runtime identity: %v", err)
	}
	cfg := integrationconfig.Config{}
	if _, err := servicekit.LoadYAMLConfigRaw(identity, &cfg); err == nil ||
		!strings.Contains(err.Error(), "integration-service.yaml") {
		t.Fatalf("unreadable snapshot must fail closed: %v", err)
	}

	mistypedRoot := t.TempDir()
	mistyped := filepath.Join(mistypedRoot, "integration-service.yaml")
	writeRuntimeConfigFile(t, mistyped, "mongodb:\n  database:\n    - not-a-string\n")
	t.Setenv("CONFIG_ROOT", mistypedRoot)
	identity, err = servicekit.ResolveIdentity("integration-service")
	if err != nil {
		t.Fatalf("resolve runtime identity: %v", err)
	}
	_, err = servicekit.LoadYAMLConfigRaw(identity, &cfg)
	if err == nil || !strings.Contains(err.Error(), "parse "+mistyped) {
		t.Fatalf("mistyped snapshot must fail closed: %v", err)
	}
}
