package application

import (
	"fmt"
	"strings"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// OperationOwnerBinding is the single generated-operation prefix to upstream
// ownership catalog consumed by api-edge composition and its contract tests.
type OperationOwnerBinding struct {
	OperationPrefix string
	UpstreamName    string
}

var operationDomains = []string{
	"assistant", "chat", "circle", "content", "entity", "integration",
	"notification", "ops", "realtime", "recommendation", "rtc", "search",
	"tag", "user",
}

var operationOwnerBindings = []OperationOwnerBinding{
	{OperationPrefix: "assistant.", UpstreamName: "assistant"},
	{OperationPrefix: "chat.", UpstreamName: "chat"},
	{OperationPrefix: "circle.", UpstreamName: "circle"},
	{OperationPrefix: "content.", UpstreamName: "content"},
	{OperationPrefix: "entity.", UpstreamName: "entity"},
	{OperationPrefix: "integration.", UpstreamName: "integration"},
	{OperationPrefix: "notification.", UpstreamName: "notification"},
	{OperationPrefix: "ops.platform_ops.", UpstreamName: "platform_ops"},
	{OperationPrefix: "ops.", UpstreamName: "ops"},
	{OperationPrefix: "realtime.", UpstreamName: "realtime"},
	{OperationPrefix: "recommendation.", UpstreamName: "recommendation"},
	{OperationPrefix: "rtc.", UpstreamName: "rtc"},
	{OperationPrefix: "search.", UpstreamName: "search"},
	{OperationPrefix: "tag.", UpstreamName: "tag"},
	{OperationPrefix: "user.", UpstreamName: "user"},
}

func AllOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	var result []rtauth.OperationSecurityDescriptor
	for _, domainName := range operationDomains {
		result = append(result, operationsecurity.ForDomain(domainName)...)
	}
	return result
}

func OperationOwnerBindings() []OperationOwnerBinding {
	return append([]OperationOwnerBinding(nil), operationOwnerBindings...)
}

func RequiredUpstreams() []string {
	result := make([]string, 0, len(operationOwnerBindings))
	seen := make(map[string]struct{}, len(operationOwnerBindings))
	for _, binding := range operationOwnerBindings {
		if _, exists := seen[binding.UpstreamName]; exists {
			continue
		}
		seen[binding.UpstreamName] = struct{}{}
		result = append(result, binding.UpstreamName)
	}
	return result
}

func ValidateDescriptorOwners(descriptors []rtauth.OperationSecurityDescriptor) error {
	if len(descriptors) == 0 {
		return fmt.Errorf("generated operation descriptor set is empty")
	}
	for _, descriptor := range descriptors {
		matched := false
		for _, binding := range operationOwnerBindings {
			if strings.HasPrefix(
				descriptor.CanonicalOperationID,
				binding.OperationPrefix,
			) {
				matched = true
				break
			}
		}
		if !matched {
			return fmt.Errorf(
				"generated operation %s has no owner upstream",
				descriptor.CanonicalOperationID,
			)
		}
	}
	return nil
}
