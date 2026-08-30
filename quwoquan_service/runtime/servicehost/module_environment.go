package servicehost

import (
	"os"
	"strings"
)

const serviceCoreModeEnvironment = "SERVICE_CORE_MODE"

// ModuleEnvironmentValue resolves a module-scoped value in service-core while
// preserving the existing standalone environment contract.
func ModuleEnvironmentValue(module string, key string) string {
	if strings.TrimSpace(os.Getenv(serviceCoreModeEnvironment)) != "1" {
		return os.Getenv(key)
	}
	if key == "SERVICE_NAME" {
		return module
	}
	scopedKey := "SERVICE_CORE_" + environmentToken(module) + "_" + key
	if value := os.Getenv(scopedKey); value != "" {
		return value
	}
	return os.Getenv(key)
}

// RuntimeIdentityEnvironment 是 mutable test-live runtime 身份校验专用的进程级
// lookup。身份的 ConfigurationDigest 绑定的是 runtime 边界（api-edge）的配置渲染，
// 而 service-core 在构建各模块期间会把 CONFIG_VERSION 覆盖为模块私有值，因此任何
// 模块校验 runtime 身份时都必须经 api-edge scope 解析 CONFIG_VERSION，其余键
// 保持进程环境原值。standalone 部署没有模块覆盖，该 lookup 退化为 os.LookupEnv。
func RuntimeIdentityEnvironment() func(string) (string, bool) {
	return func(key string) (string, bool) {
		if key == "CONFIG_VERSION" {
			value := ModuleEnvironmentValue("api-edge", key)
			return value, value != ""
		}
		return os.LookupEnv(key)
	}
}

func environmentToken(value string) string {
	var token strings.Builder
	for _, character := range strings.ToUpper(strings.TrimSpace(value)) {
		switch {
		case character >= 'A' && character <= 'Z':
			token.WriteRune(character)
		case character >= '0' && character <= '9':
			token.WriteRune(character)
		default:
			token.WriteByte('_')
		}
	}
	return token.String()
}
