package objectstorage

import (
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
)

const objectStorageCapabilityID = "runtime.object.storage"

// Binding is the compiler-selected object-storage adapter materialization.
type Binding struct {
	AdapterID       string
	Endpoint        string
	AccessKeyID     string
	AccessKeySecret string
	Timeout         time.Duration
}

// LoadBinding materializes runtime.object.storage from the generated Binding descriptor.
func LoadBinding(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (Binding, error) {
	if configProvider == nil {
		return Binding{}, fmt.Errorf("runtime.object.storage binding has no runtime config provider")
	}
	descriptor, found := contentgenerated.CompiledBindingFor(objectStorageCapabilityID)
	if !found || descriptor.State != "enabled" {
		return Binding{}, fmt.Errorf(
			"runtime.object.storage binding is unavailable for environment=%s",
			appEnv,
		)
	}
	switch descriptor.AdapterID {
	case MinIOAdapterID, S3CompatibleAdapterID:
	default:
		return Binding{}, fmt.Errorf(
			"runtime.object.storage selects unsupported adapter=%s",
			descriptor.AdapterID,
		)
	}
	endpointKey := strings.TrimSpace(descriptor.EndpointEnvironmentKeys["endpoint"])
	if endpointKey == "" {
		return Binding{}, fmt.Errorf("runtime.object.storage binding has no endpoint reference")
	}
	endpoint, endpointOK := configProvider.GetString(endpointKey)
	if !endpointOK || strings.TrimSpace(endpoint) == "" {
		return Binding{}, fmt.Errorf(
			"runtime.object.storage endpoint material is unavailable for environment=%s",
			appEnv,
		)
	}
	secrets := make(map[string]string, len(descriptor.SecretEnvironmentKeys))
	for _, key := range descriptor.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(key)
		if !ok || strings.TrimSpace(value) == "" {
			return Binding{}, fmt.Errorf(
				"runtime.object.storage secret material is unavailable for environment=%s",
				appEnv,
			)
		}
		secrets[key] = value
	}
	return Binding{
		AdapterID:       descriptor.AdapterID,
		Endpoint:        strings.TrimSpace(endpoint),
		AccessKeyID:     strings.TrimSpace(secrets["CONTENT_OSS_ACCESS_KEY_ID"]),
		AccessKeySecret: strings.TrimSpace(secrets["CONTENT_OSS_ACCESS_KEY_SECRET"]),
		Timeout:         time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond,
	}, nil
}
