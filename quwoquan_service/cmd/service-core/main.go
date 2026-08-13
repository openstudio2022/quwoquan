package main

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"quwoquan_service/runtime/servicehost"
	apiedge "quwoquan_service/services/api-edge/cmd/api"
	assistant "quwoquan_service/services/assistant-service/cmd/api"
	chat "quwoquan_service/services/chat-service/cmd/api"
	circle "quwoquan_service/services/circle-service/cmd/api"
	content "quwoquan_service/services/content-service/cmd/api"
	entity "quwoquan_service/services/entity-service/cmd/api"
	integration "quwoquan_service/services/integration-service/cmd/api"
	notification "quwoquan_service/services/notification-service/cmd/api"
	search "quwoquan_service/services/search-service/cmd/api"
	tag "quwoquan_service/services/tag-service/cmd/api"
	user "quwoquan_service/services/user-service/cmd/api"

	"gopkg.in/yaml.v3"
)

const (
	compositionProfile                          = "service-core"
	entityAccountSecurityAuthorityBaseURLEnvKey = "ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL"
)

//go:embed composition.yaml
var compositionManifestBytes []byte

type compositionManifest struct {
	Schema  string                      `yaml:"schema"`
	Profile string                      `yaml:"profile"`
	Modules []compositionManifestModule `yaml:"modules"`
}

type compositionManifestModule struct {
	Name               string `yaml:"name"`
	Host               string `yaml:"host"`
	Port               int    `yaml:"port"`
	AddressEnvironment string `yaml:"addressEnvironment"`
	InternalAddress    string `yaml:"internalAddress"`
}

func main() {
	describeComposition := flag.Bool(
		"describe-composition",
		false,
		"print the immutable service-core composition identity and exit",
	)
	describeTopology := flag.Bool(
		"describe-topology",
		false,
		"print topology identity from repeated --module-config-digest name=digest values",
	)
	preflightOnly := flag.Bool(
		"preflight-only",
		false,
		"construct and validate every module without binding listeners or starting workers",
	)
	moduleConfigDigests := make(map[string]string)
	flag.Func(
		"module-config-digest",
		"module config identity in name=digest form; repeat for every module",
		func(raw string) error {
			name, digest, found := strings.Cut(raw, "=")
			name = strings.TrimSpace(name)
			digest = strings.TrimSpace(digest)
			if !found || name == "" || digest == "" {
				return errors.New("module config digest must use non-empty name=digest")
			}
			if _, exists := moduleConfigDigests[name]; exists {
				return fmt.Errorf("module config digest %q is duplicated", name)
			}
			moduleConfigDigests[name] = digest
			return nil
		},
	)
	flag.Parse()

	factories, endpoints, err := canonicalCompositionInputs()
	if err != nil {
		slog.Error("service-core manifest is invalid", "error", err)
		os.Exit(1)
	}
	composition, err := servicehost.NewCompositionWithEndpoints(
		compositionProfile,
		endpoints,
		factories...,
	)
	if err != nil {
		slog.Error("service-core composition is invalid", "error", err)
		os.Exit(1)
	}
	if *describeComposition {
		if err := json.NewEncoder(os.Stdout).Encode(composition.Identity()); err != nil {
			slog.Error("service-core composition identity encoding failed", "error", err)
			os.Exit(1)
		}
		return
	}
	if *describeTopology {
		configs := make([]servicehost.ModuleConfigIdentity, 0, len(factories))
		for _, factory := range factories {
			digest, exists := moduleConfigDigests[factory.Name]
			if !exists {
				slog.Error(
					"service-core topology config identity is incomplete",
					"module",
					factory.Name,
				)
				os.Exit(1)
			}
			configs = append(configs, servicehost.ModuleConfigIdentity{
				Name:         factory.Name,
				ConfigDigest: digest,
			})
		}
		if len(moduleConfigDigests) != len(configs) {
			slog.Error("service-core topology config identity contains unknown modules")
			os.Exit(1)
		}
		topology, err := composition.ResolveDeclaredTopologyIdentity(configs)
		if err != nil {
			slog.Error("service-core topology identity is invalid", "error", err)
			os.Exit(1)
		}
		if err := json.NewEncoder(os.Stdout).Encode(topology); err != nil {
			slog.Error("service-core topology identity encoding failed", "error", err)
			os.Exit(1)
		}
		return
	}
	if *preflightOnly {
		if err := runPreflight(composition); err != nil {
			slog.Error("service-core preflight failed", "error", err)
			os.Exit(1)
		}
		return
	}
	if err := run(composition); err != nil {
		slog.Error("service-core stopped with failure", "error", err)
		os.Exit(1)
	}
}

func runPreflight(composition *servicehost.Composition) error {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		return err
	}
	modules, err := composition.Build(ctx)
	if err != nil {
		return errors.Join(err, shutdownRouter(router))
	}
	host, err := servicehost.NewSupervisor(modules...)
	if err != nil {
		return errors.Join(
			errorsWithShutdown(modules, err),
			shutdownRouter(router),
		)
	}
	var result error
	for _, module := range modules {
		if err := module.ValidateConfig(ctx); err != nil {
			result = errors.Join(
				result,
				fmt.Errorf("module %q validation: %w", module.Name(), err),
			)
			break
		}
		if err := module.PrepareMigration(ctx); err != nil {
			result = errors.Join(
				result,
				fmt.Errorf("module %q migration: %w", module.Name(), err),
			)
			break
		}
	}
	shutdownCtx, shutdownCancel := context.WithTimeout(
		context.Background(),
		45*time.Second,
	)
	defer shutdownCancel()
	return errors.Join(
		result,
		host.Shutdown(shutdownCtx),
		router.Shutdown(shutdownCtx),
	)
}

func run(composition *servicehost.Composition) error {
	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		return err
	}
	if err := router.Bind(ctx); err != nil {
		return err
	}
	if err := router.Start(ctx); err != nil {
		return errors.Join(err, shutdownRouter(router))
	}
	modules, err := composition.Build(ctx)
	if err != nil {
		return errors.Join(err, shutdownRouter(router))
	}
	topology, err := composition.ResolveTopologyIdentity(modules)
	if err != nil {
		return errors.Join(
			errorsWithShutdown(modules, err),
			shutdownRouter(router),
		)
	}
	host, err := servicehost.NewSupervisor(modules...)
	if err != nil {
		return errors.Join(
			errorsWithShutdown(modules, err),
			shutdownRouter(router),
		)
	}
	slog.Info(
		"service-core topology resolved",
		"compositionDigest",
		topology.CompositionDigest,
		"topologyDigest",
		topology.TopologyDigest,
		"modules",
		strings.Join(composition.Identity().Modules, ","),
	)
	if err := host.Start(ctx); err != nil {
		return errors.Join(err, shutdownRouter(router))
	}
	if err := router.Ready(ctx); err != nil {
		return errors.Join(
			err,
			host.Shutdown(context.Background()),
			shutdownRouter(router),
		)
	}
	router.OpenAdmission()
	<-ctx.Done()

	router.CloseAdmission()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	return errors.Join(
		host.Shutdown(shutdownCtx),
		router.Shutdown(shutdownCtx),
	)
}

func canonicalCompositionInputs() (
	[]servicehost.ModuleFactory,
	[]servicehost.EndpointIdentity,
	error,
) {
	manifest, err := loadCompositionManifest()
	if err != nil {
		return nil, nil, err
	}
	bindings := map[string]func() (servicehost.Module, error){
		"user-service":         moduleFactory("user-service", user.NewModule).New,
		"integration-service":  moduleFactory("integration-service", integration.NewModule).New,
		"notification-service": moduleFactory("notification-service", notification.NewModule).New,
		"entity-service":       moduleFactory("entity-service", entity.NewModule).New,
		"tag-service":          moduleFactory("tag-service", tag.NewModule).New,
		"search-service":       moduleFactory("search-service", search.NewModule).New,
		"content-service":      moduleFactory("content-service", content.NewModule).New,
		"circle-service":       moduleFactory("circle-service", circle.NewModule).New,
		"chat-service":         moduleFactory("chat-service", chat.NewModule).New,
		"assistant-service":    moduleFactory("assistant-service", assistant.NewModule).New,
		"api-edge":             moduleFactory("api-edge", apiedge.NewModule).New,
	}
	factories := make([]servicehost.ModuleFactory, 0, len(manifest.Modules))
	endpoints := make([]servicehost.EndpointIdentity, 0, len(manifest.Modules))
	seen := make(map[string]struct{}, len(manifest.Modules))
	for _, module := range manifest.Modules {
		constructor := bindings[module.Name]
		if constructor == nil {
			return nil, nil, fmt.Errorf(
				"service-core module %q has no bootstrap binding",
				module.Name,
			)
		}
		if _, exists := seen[module.Name]; exists {
			return nil, nil, fmt.Errorf(
				"service-core module %q is duplicated",
				module.Name,
			)
		}
		seen[module.Name] = struct{}{}
		factories = append(factories, servicehost.ModuleFactory{
			Name: module.Name,
			New:  constructor,
		})
		endpoints = append(endpoints, servicehost.EndpointIdentity{
			Module: module.Name,
			Host:   module.Host,
			Port:   module.Port,
		})
	}
	if len(seen) != len(bindings) {
		return nil, nil, fmt.Errorf(
			"service-core manifest identifies %d of %d bootstrap modules",
			len(seen),
			len(bindings),
		)
	}
	return factories, endpoints, nil
}

func prepareVirtualHTTPRouting() (*servicehost.VirtualHTTPRouter, error) {
	if err := os.Setenv("SERVICE_CORE_MODE", "1"); err != nil {
		return nil, fmt.Errorf("enable service-core module environment: %w", err)
	}
	manifest, err := loadCompositionManifest()
	if err != nil {
		return nil, err
	}
	routes := make([]servicehost.VirtualHTTPRoute, 0, len(manifest.Modules))
	userServiceInternalAddress := ""
	for _, module := range manifest.Modules {
		if module.AddressEnvironment == "" && module.InternalAddress == "" {
			continue
		}
		if module.AddressEnvironment == "" || module.InternalAddress == "" {
			return nil, fmt.Errorf(
				"service-core module %q has incomplete virtual listener",
				module.Name,
			)
		}
		if err := os.Setenv(module.AddressEnvironment, module.InternalAddress); err != nil {
			return nil, fmt.Errorf(
				"set service-core module address %s: %w",
				module.AddressEnvironment,
				err,
			)
		}
		if module.Name == "user-service" {
			userServiceInternalAddress = module.InternalAddress
		}
		routes = append(routes, servicehost.VirtualHTTPRoute{
			Host:       module.Host,
			PublicAddr: fmt.Sprintf(":%d", module.Port),
			Upstream:   "http://" + module.InternalAddress,
		})
	}
	if userServiceInternalAddress == "" {
		return nil, errors.New(
			"service-core user-service internal topology is unavailable",
		)
	}
	if err := os.Setenv(
		entityAccountSecurityAuthorityBaseURLEnvKey,
		"http://"+userServiceInternalAddress,
	); err != nil {
		return nil, fmt.Errorf(
			"set service-core entity account security authority endpoint: %w",
			err,
		)
	}
	return servicehost.NewVirtualHTTPRouter(routes...)
}

func loadCompositionManifest() (compositionManifest, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(compositionManifestBytes))
	decoder.KnownFields(true)
	var manifest compositionManifest
	if err := decoder.Decode(&manifest); err != nil {
		return compositionManifest{}, fmt.Errorf(
			"decode service-core composition manifest: %w",
			err,
		)
	}
	if manifest.Schema != "quwoquan.service_core_manifest.v1" {
		return compositionManifest{}, fmt.Errorf(
			"service-core composition schema %q is unsupported",
			manifest.Schema,
		)
	}
	if manifest.Profile != compositionProfile {
		return compositionManifest{}, fmt.Errorf(
			"service-core composition profile %q is invalid",
			manifest.Profile,
		)
	}
	if len(manifest.Modules) == 0 {
		return compositionManifest{}, errors.New(
			"service-core composition has no modules",
		)
	}
	return manifest, nil
}

func moduleFactory[T servicehost.Module](
	name string,
	constructor func() (T, error),
) servicehost.ModuleFactory {
	return servicehost.ModuleFactory{
		Name: name,
		New: func() (servicehost.Module, error) {
			restore, err := applyModuleEnvironment(name)
			if err != nil {
				return nil, err
			}
			defer restore()
			module, err := constructor()
			if err != nil {
				return nil, err
			}
			return module, nil
		},
	}
}

func applyModuleEnvironment(name string) (func(), error) {
	overrides := map[string]string{
		"SERVICE_NAME": name,
	}
	configVersion := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue(name, "CONFIG_VERSION"),
	)
	if configVersion == "" {
		return nil, fmt.Errorf(
			"service-core module %q config version is missing",
			name,
		)
	}
	overrides["CONFIG_VERSION"] = configVersion
	if instanceID := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue(name, "SERVICE_INSTANCE_ID"),
	); instanceID != "" {
		overrides["SERVICE_INSTANCE_ID"] = instanceID
	}
	type previousValue struct {
		value  string
		exists bool
	}
	previous := make(map[string]previousValue, len(overrides))
	for key, value := range overrides {
		old, exists := os.LookupEnv(key)
		previous[key] = previousValue{value: old, exists: exists}
		if err := os.Setenv(key, value); err != nil {
			return nil, fmt.Errorf("set service-core module environment %s: %w", key, err)
		}
	}
	return func() {
		for key, old := range previous {
			if old.exists {
				_ = os.Setenv(key, old.value)
			} else {
				_ = os.Unsetenv(key)
			}
		}
	}, nil
}

func errorsWithShutdown(modules []servicehost.Module, cause error) error {
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	result := cause
	for index := len(modules) - 1; index >= 0; index-- {
		if err := modules[index].Shutdown(shutdownCtx); err != nil {
			result = errors.Join(result, fmt.Errorf(
				"module %q construction cleanup: %w",
				modules[index].Name(),
				err,
			))
		}
	}
	return result
}

func shutdownRouter(router *servicehost.VirtualHTTPRouter) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return router.Shutdown(ctx)
}
