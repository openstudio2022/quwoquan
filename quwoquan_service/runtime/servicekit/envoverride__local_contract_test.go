package servicekit

import (
	"reflect"
	"strings"
	"testing"
)

type envOverrideFixture struct {
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr" env:"SERVICE_ADDR"`
		} `yaml:"http"`
	} `yaml:"service"`
	Mongo struct {
		URI string `yaml:"uri" env:"MONGO_URI"`
	} `yaml:"mongo"`
	Redis struct {
		General struct {
			Mode  string   `yaml:"mode" env:"MODE"`
			Addrs []string `yaml:"addrs" env:"ADDRS"`
			TLS   bool     `yaml:"tls" env:"TLS"`
			DB    int      `yaml:"db" env:"DB"`
		} `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`
}

func TestApplyEnvOverridesTypeMatrixAndSegmentedKeys(t *testing.T) {
	t.Setenv("FIX_SERVICE_ADDR", "  :19001  ")
	t.Setenv("FIX_MONGO_URI", "mongodb://db.internal:27017")
	t.Setenv("FIX_REDIS_GENERAL_MODE", "cluster")
	t.Setenv("FIX_REDIS_GENERAL_ADDRS", "a:6379,b:6379")
	t.Setenv("FIX_REDIS_GENERAL_TLS", "yes")
	t.Setenv("FIX_REDIS_GENERAL_DB", "3")

	cfg := envOverrideFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":19001" {
		t.Fatalf("expected TrimSpace-applied addr, got %q", cfg.Service.HTTP.Addr)
	}
	if cfg.Mongo.URI != "mongodb://db.internal:27017" {
		t.Fatalf("unexpected mongo uri %q", cfg.Mongo.URI)
	}
	if cfg.Redis.General.Mode != "cluster" {
		t.Fatalf("expected nested envPrefix key to apply, got %q", cfg.Redis.General.Mode)
	}
	if !reflect.DeepEqual(cfg.Redis.General.Addrs, []string{"a:6379", "b:6379"}) {
		t.Fatalf("expected comma-split addrs, got %v", cfg.Redis.General.Addrs)
	}
	if !cfg.Redis.General.TLS {
		t.Fatal("expected truthy TLS literal to apply")
	}
	if cfg.Redis.General.DB != 3 {
		t.Fatalf("expected int override, got %d", cfg.Redis.General.DB)
	}
}

func TestApplyEnvOverridesEmptyEnvDoesNotOverride(t *testing.T) {
	t.Setenv("FIX_SERVICE_ADDR", "   ")
	cfg := envOverrideFixture{}
	cfg.Service.HTTP.Addr = ":18092"
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Service.HTTP.Addr != ":18092" {
		t.Fatalf("blank env must keep the snapshot value, got %q", cfg.Service.HTTP.Addr)
	}
}

func TestApplyEnvOverridesFalsyBoolOverridesToFalse(t *testing.T) {
	t.Setenv("FIX_REDIS_GENERAL_TLS", "off")
	cfg := envOverrideFixture{}
	cfg.Redis.General.TLS = true
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Redis.General.TLS {
		t.Fatal("expected falsy literal to override to false")
	}
}

func TestApplyEnvOverridesRejectsInvalidLiterals(t *testing.T) {
	t.Setenv("FIX_REDIS_GENERAL_TLS", "maybe")
	cfg := envOverrideFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err == nil ||
		!strings.Contains(err.Error(), "FIX_REDIS_GENERAL_TLS") {
		t.Fatalf("expected boolean literal rejection, got %v", err)
	}

	t.Setenv("FIX_REDIS_GENERAL_TLS", "")
	t.Setenv("FIX_REDIS_GENERAL_DB", "not-a-number")
	cfg = envOverrideFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err == nil ||
		!strings.Contains(err.Error(), "FIX_REDIS_GENERAL_DB") {
		t.Fatalf("expected integer literal rejection, got %v", err)
	}
}

func TestApplyEnvOverridesFailsClosedOnUnsupportedType(t *testing.T) {
	type badFixture struct {
		Labels map[string]string `env:"LABELS"`
	}
	t.Setenv("FIX_LABELS", "a=1")
	cfg := badFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err == nil ||
		!strings.Contains(err.Error(), "unsupported field type") {
		t.Fatalf("expected unsupported type rejection, got %v", err)
	}
}

// 浮点覆盖是坐标一类配置的真实形态：数值可写入，非数值必须阻断而不是
// 静默留在零值。
func TestApplyEnvOverridesAppliesFloatValues(t *testing.T) {
	type coordinateFixture struct {
		Latitude float64 `env:"LATITUDE"`
	}
	t.Setenv("FIX_LATITUDE", "31.2304")
	cfg := coordinateFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("apply float override: %v", err)
	}
	if cfg.Latitude != 31.2304 {
		t.Fatalf("float override drift: %v", cfg.Latitude)
	}

	t.Setenv("FIX_LATITUDE", "not-a-number")
	cfg = coordinateFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err == nil ||
		!strings.Contains(err.Error(), "must be numeric") {
		t.Fatalf("expected numeric rejection, got %v", err)
	}
}

// 逗号列表逐项去空白并丢弃空项：部署面模板的尾随分隔符不得变成一个空地址。
func TestApplyEnvOverridesTrimsAndDropsEmptyListItems(t *testing.T) {
	t.Setenv("FIX_REDIS_GENERAL_ADDRS", " redis-0:6379 , ,redis-1:6379 ")
	cfg := envOverrideFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("apply list override: %v", err)
	}
	if strings.Join(cfg.Redis.General.Addrs, "|") != "redis-0:6379|redis-1:6379" {
		t.Fatalf("list override drift: %#v", cfg.Redis.General.Addrs)
	}

	t.Setenv("FIX_REDIS_GENERAL_ADDRS", " , ")
	cfg = envOverrideFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err == nil ||
		!strings.Contains(err.Error(), "must list at least one non-empty value") {
		t.Fatalf("expected empty list rejection, got %v", err)
	}
}

func TestEnvOverrideKeysListsDeclaredKeys(t *testing.T) {
	keys, err := EnvOverrideKeys("TAG", &envOverrideFixture{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	expected := []string{
		"TAG_SERVICE_ADDR",
		"TAG_MONGO_URI",
		"TAG_REDIS_GENERAL_MODE",
		"TAG_REDIS_GENERAL_ADDRS",
		"TAG_REDIS_GENERAL_TLS",
		"TAG_REDIS_GENERAL_DB",
	}
	if !reflect.DeepEqual(keys, expected) {
		t.Fatalf("declared keys drifted:\n got %v\nwant %v", keys, expected)
	}
}

func TestValidateRequiredRunsAfterEnvOverride(t *testing.T) {
	type requiredFixture struct {
		Mongo struct {
			URI string `yaml:"uri" env:"MONGO_URI" required:"true"`
		} `yaml:"mongo"`
	}

	cfg := requiredFixture{}
	if err := ValidateRequired(&cfg); err == nil ||
		!strings.Contains(err.Error(), "Mongo.URI") {
		t.Fatalf("expected required rejection for missing value, got %v", err)
	}

	// required 校验时机在 env 覆盖之后：快照缺值但 env 提供即通过。
	t.Setenv("FIX_MONGO_URI", "mongodb://db.internal:27017")
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := ValidateRequired(&cfg); err != nil {
		t.Fatalf("required must pass after env override, got %v", err)
	}
}

func TestValidateRequiredRejectsNonStringFields(t *testing.T) {
	type badRequired struct {
		Port int `required:"true"`
	}
	cfg := badRequired{Port: 8080}
	if err := ValidateRequired(&cfg); err == nil ||
		!strings.Contains(err.Error(), "only supports string") {
		t.Fatalf("expected non-string required rejection, got %v", err)
	}
}

// TestApplyEnvOverridesSupportsAbsoluteContractKeys 锁定 envAbsolute：环境
// 装配契约已固定为无前缀的键（如 secretRefs 的 MONGO_URI）不得被前缀污染。
func TestApplyEnvOverridesSupportsAbsoluteContractKeys(t *testing.T) {
	type absoluteFixture struct {
		MongoDB struct {
			URI      string `yaml:"uri" envAbsolute:"MONGO_URI"`
			Database string `yaml:"database" envAbsolute:"MONGO_DATABASE"`
		} `yaml:"mongodb"`
	}
	t.Setenv("MONGO_URI", "mongodb://db.internal:27017")
	t.Setenv("MONGO_DATABASE", "quwoquan_rtc")
	t.Setenv("FIX_MONGO_URI", "must-not-apply")

	cfg := absoluteFixture{}
	if err := ApplyEnvOverrides("FIX", &cfg); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.MongoDB.URI != "mongodb://db.internal:27017" {
		t.Fatalf("absolute key must win over prefixed key, got %q", cfg.MongoDB.URI)
	}
	if cfg.MongoDB.Database != "quwoquan_rtc" {
		t.Fatalf("unexpected database %q", cfg.MongoDB.Database)
	}

	keys, err := EnvOverrideKeys("FIX", &absoluteFixture{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !reflect.DeepEqual(keys, []string{"MONGO_URI", "MONGO_DATABASE"}) {
		t.Fatalf("absolute keys must be listed without prefix, got %v", keys)
	}
}

func TestApplyEnvOverridesRejectsConflictingEnvTags(t *testing.T) {
	type conflicting struct {
		URI string `env:"MONGO_URI" envAbsolute:"MONGO_URI"`
	}
	if err := ApplyEnvOverrides("FIX", &conflicting{}); err == nil ||
		!strings.Contains(err.Error(), "both env and envAbsolute") {
		t.Fatalf("expected conflicting tag rejection, got %v", err)
	}
}

func TestApplyEnvOverridesRequiresStructPointer(t *testing.T) {
	if err := ApplyEnvOverrides("FIX", envOverrideFixture{}); err == nil {
		t.Fatal("expected rejection for non-pointer target")
	}
	var nilTarget *envOverrideFixture
	if err := ApplyEnvOverrides("FIX", nilTarget); err == nil {
		t.Fatal("expected rejection for nil pointer target")
	}
}
