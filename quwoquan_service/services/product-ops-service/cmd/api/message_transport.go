package main

import (
	"context"
	"fmt"
	"slices"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	experimentbinding "quwoquan_service/services/product-ops-service/generated/product_ops/experiment"
	premiumpoolbinding "quwoquan_service/services/product-ops-service/generated/product_ops/premium_pool_entry"
)

const productOpsAPIMessageTransportRoot = "product-ops-service-api"

func requireMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := experimentbinding.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	premiumBinding, premiumFound := premiumpoolbinding.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	if premiumFound != found ||
		premiumBinding.State != binding.State ||
		premiumBinding.AdapterID != binding.AdapterID ||
		premiumBinding.TimeoutMilliseconds != binding.TimeoutMilliseconds ||
		!slices.Equal(
			premiumBinding.RequiredRedisScenes,
			binding.RequiredRedisScenes,
		) {
		return nil, fmt.Errorf(
			"product-ops message transport bindings disagree for environment=%s",
			environment,
		)
	}
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, found,
		runtimemessaging.MessageTransportBinding{
			State: binding.State, AdapterID: binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              productOpsAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	general, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf("message transport root %s is missing general scene", productOpsAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		productOpsAPIMessageTransportRoot, binding.AdapterID, general, general,
	)
}
