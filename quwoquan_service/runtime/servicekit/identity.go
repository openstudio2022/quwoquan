package servicekit

import (
	"fmt"
	"os"
	"strings"

	"quwoquan_service/runtime/servicehost"
)

// Identity 是一个服务模块的运行时身份：进程注入的四元组
// （SERVICE_NAME/APP_ENV/CONFIG_VERSION/IMAGE_VERSION）加配置根与实例标识。
// 它由部署面注入、启动期一次解析，之后只读传递。
type Identity struct {
	ServiceName   string
	AppEnv        string
	ConfigRoot    string
	ConfigVersion string
	ImageVersion  string
	InstanceID    string
}

// ResolveIdentity 解析并校验模块运行时身份。serviceName 是该模块在
// composition.yaml、compose service name 与 specs 中共用的同一字面值，
// 也是 service-core 模式下模块作用域环境变量的解析键。
func ResolveIdentity(serviceName string) (Identity, error) {
	declared := strings.TrimSpace(serviceName)
	if declared == "" {
		return Identity{}, fmt.Errorf("service name is required")
	}
	resolved := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue(declared, "SERVICE_NAME"),
	)
	if resolved == "" {
		resolved = declared
	}

	appEnv := os.Getenv("APP_ENV")
	if appEnv == "" {
		appEnv = "alpha"
	}
	if !IsValidAppEnv(appEnv) {
		return Identity{}, fmt.Errorf(
			"APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv,
		)
	}

	configVersion := servicehost.ModuleEnvironmentValue(declared, "CONFIG_VERSION")
	if RequiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return Identity{}, fmt.Errorf(
			"CONFIG_VERSION is required when APP_ENV=%s", appEnv,
		)
	}

	instanceID := strings.TrimSpace(os.Getenv("SERVICE_INSTANCE_ID"))
	if instanceID == "" {
		hostname, _ := os.Hostname()
		instanceID = strings.TrimSpace(hostname)
	}
	if instanceID == "" {
		instanceID = resolved
	}

	return Identity{
		ServiceName:   resolved,
		AppEnv:        appEnv,
		ConfigRoot:    os.Getenv("CONFIG_ROOT"),
		ConfigVersion: configVersion,
		ImageVersion:  os.Getenv("IMAGE_VERSION"),
		InstanceID:    instanceID,
	}, nil
}

// IsValidAppEnv 判定四环境白名单。
func IsValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

// RequiresConfigVersion 判定该环境是否强制 CONFIG_VERSION digest 钉住配置快照。
func RequiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

// ServiceBaseURLKey 派生跨服务调用地址的统一环境键名：
// 服务名大写、非字母数字折叠为下划线，再接 _BASE_URL。
// 例如 content-service -> CONTENT_SERVICE_BASE_URL、platform-ops -> PLATFORM_OPS_BASE_URL。
// 值仍由部署面或宿主注入，本包只收敛键名规约。
func ServiceBaseURLKey(serviceName string) string {
	return environmentToken(serviceName) + "_BASE_URL"
}

// ServiceBaseURL 读取目标服务按统一键名规约注入的物理地址；未注入时返回空串，
// 是否 fail 由调用方按依赖必需性裁决。
func (identity Identity) ServiceBaseURL(targetServiceName string) string {
	return strings.TrimSpace(os.Getenv(ServiceBaseURLKey(targetServiceName)))
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
