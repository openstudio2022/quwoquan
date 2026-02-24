package runtimeobservability

import (
	"net/http"
	"strings"
)

type servicePreset struct {
	serviceName     string
	sourceID        string
	src             string
	origin          string
	direction       string
	configPrefix    string
	endpointMapping map[string]string
}

func NewGatewayClient(
	baseTransport http.RoundTripper,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) *http.Client {
	return newServicePresetClient(baseTransport, ioLogger, processLogger, exceptionLogger, servicePreset{
		serviceName:  "gateway-service",
		sourceID:     "gateway-service",
		src:          defaultSourceService,
		origin:       "service.http",
		direction:    DirectionOutbound,
		configPrefix: "sys.gateway.http_client",
		endpointMapping: map[string]string{
			"GET:/v1/orch/discovery/feed": "orch.discovery_feed.list",
			"POST:/v1/chat/conversations": "chat.conversation.create",
		},
	})
}

func NewOrchestratorClient(
	baseTransport http.RoundTripper,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
) *http.Client {
	return newServicePresetClient(baseTransport, ioLogger, processLogger, exceptionLogger, servicePreset{
		serviceName:  "orchestrator-service",
		sourceID:     "orchestrator-service",
		src:          defaultSourceService,
		origin:       "service.http",
		direction:    DirectionOutbound,
		configPrefix: "sys.orchestrator.http_client",
		endpointMapping: map[string]string{
			"GET:/v1/content/feed":                     "content.feed.list",
			"GET:/v1/circles/{circleId}/activities":   "orch.circle.activities.list",
			"POST:/v1/ops/events":                      "ops.events.ingest",
		},
	})
}

func NewContentClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "content-service")
}

func NewCircleClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "circle-service")
}

func NewUserClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "user-service")
}

func NewChatClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "chat-service")
}

func NewAssistantClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "assistant-service")
}

func NewProductOpsClient(baseTransport http.RoundTripper, ioLogger *IOAccessLogger, processLogger *ProcessTraceLogger, exceptionLogger *ExceptionLogger) *http.Client {
	return newSimpleServiceClient(baseTransport, ioLogger, processLogger, exceptionLogger, "product-ops")
}

func newSimpleServiceClient(
	baseTransport http.RoundTripper,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
	serviceName string,
) *http.Client {
	return newServicePresetClient(baseTransport, ioLogger, processLogger, exceptionLogger, servicePreset{
		serviceName:     serviceName,
		sourceID:        serviceName,
		src:             defaultSourceService,
		origin:          "service.http",
		direction:       DirectionOutbound,
		configPrefix:    "sys." + strings.ReplaceAll(strings.ReplaceAll(serviceName, "-service", ""), "-", "_") + ".http_client",
		endpointMapping: map[string]string{},
	})
}

func newServicePresetClient(
	baseTransport http.RoundTripper,
	ioLogger *IOAccessLogger,
	processLogger *ProcessTraceLogger,
	exceptionLogger *ExceptionLogger,
	preset servicePreset,
) *http.Client {
	configProvider := DefaultHTTPClientFactoryConfig().RuntimeConfig
	instanceID := preset.serviceName
	instanceConfigKey := preset.configPrefix + ".instance_id"
	if v, ok := configProvider.GetString(instanceConfigKey); ok {
		instanceID = v
	}

	return NewObservedHTTPClient(
		baseTransport,
		HTTPClientFactoryConfig{
			RuntimeConfig: configProvider,
			ConfigPrefix:  preset.configPrefix,
		},
		HTTPClientMiddlewareConfig{
			Service:           preset.serviceName,
			Origin:            preset.origin,
			Direction:         preset.direction,
			SourceID:          preset.sourceID,
			Src:               preset.src,
			ServiceName:       preset.serviceName,
			ServiceInstanceID: instanceID,
			EndpointResolver:  preset.endpointResolver(),
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
}

func (p servicePreset) endpointResolver() func(r *http.Request) string {
	return func(r *http.Request) string {
		key := strings.ToUpper(r.Method) + ":" + r.URL.Path
		if endpoint, ok := p.endpointMapping[key]; ok {
			return endpoint
		}
		return fallbackEndpointName(p.serviceName, r.Method, r.URL.Path)
	}
}

func fallbackEndpointName(serviceName string, method string, path string) string {
	svc := strings.ReplaceAll(serviceName, "-service", "")
	svc = strings.ReplaceAll(svc, "-", "_")
	normalizedPath := strings.Trim(path, "/")
	if normalizedPath == "" {
		normalizedPath = "root"
	}
	parts := strings.Split(normalizedPath, "/")
	for i, part := range parts {
		if strings.HasPrefix(part, "{") && strings.HasSuffix(part, "}") {
			parts[i] = "id"
			continue
		}
		parts[i] = strings.ReplaceAll(part, "-", "_")
	}
	return svc + "." + strings.ToLower(method) + "." + strings.Join(parts, "_")
}

