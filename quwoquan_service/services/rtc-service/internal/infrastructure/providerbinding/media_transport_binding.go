package providerbinding

import (
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	rtcgenerated "quwoquan_service/services/rtc-service/internal/generated"
)

const mediaTransportCapabilityID = "rtc.room.transport"

// MediaTransportBinding 是仅在组合根使用的已物化 Binding。
// 它绝不能进入 application/domain 或 HTTP 响应。
type MediaTransportBinding struct {
	AdapterID     string
	ConnectionURL string
	APIKey        string
	APISecret     string
	Timeout       time.Duration
}

// ResolveMediaTransport 要求当前环境的编译期 Binding 已启用且所有引用材料存在。
// 它不扫描 registry，也不猜测或切换 Adapter。
func ResolveMediaTransport(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (MediaTransportBinding, error) {
	if configProvider == nil {
		return MediaTransportBinding{}, fmt.Errorf("rtc media transport has no runtime config provider")
	}
	binding, found := rtcgenerated.ExternalProviderBindingFor(
		appEnv,
		mediaTransportCapabilityID,
	)
	if !found {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport binding is missing for environment=%s",
			appEnv,
		)
	}
	if binding.State != "enabled" {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport binding is not enabled for environment=%s",
			appEnv,
		)
	}
	if strings.TrimSpace(binding.AdapterID) == "" || binding.TimeoutMilliseconds <= 0 {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport binding is incomplete for environment=%s",
			appEnv,
		)
	}
	endpointKey := strings.TrimSpace(binding.EndpointEnvironmentKeys["connection"])
	if endpointKey == "" {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport binding has no connection endpoint for environment=%s",
			appEnv,
		)
	}
	connectionURL, ok := configProvider.GetString(endpointKey)
	if !ok {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport connection material is unavailable for environment=%s",
			appEnv,
		)
	}
	secrets := make(map[string]string, len(binding.SecretEnvironmentKeys))
	for _, key := range binding.SecretEnvironmentKeys {
		value, found := configProvider.GetString(key)
		if !found {
			return MediaTransportBinding{}, fmt.Errorf(
				"rtc media transport secret material is unavailable for environment=%s",
				appEnv,
			)
		}
		secrets[key] = value
	}
	apiKey := strings.TrimSpace(secrets["RTC_MEDIA_API_KEY"])
	apiSecret := strings.TrimSpace(secrets["RTC_MEDIA_API_SECRET"])
	if apiKey == "" || apiSecret == "" {
		return MediaTransportBinding{}, fmt.Errorf(
			"rtc media transport credential binding is incomplete for environment=%s",
			appEnv,
		)
	}
	return MediaTransportBinding{
		AdapterID:     binding.AdapterID,
		ConnectionURL: connectionURL,
		APIKey:        apiKey,
		APISecret:     apiSecret,
		Timeout:       time.Duration(binding.TimeoutMilliseconds) * time.Millisecond,
	}, nil
}
