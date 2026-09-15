package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
)

// serviceCoreContentMongoHandle 是 service-core 构造测试的唯一 Mongo seam。
// 它返回真实驱动 database handle，但不建立第二条网络连接。
type serviceCoreContentMongoHandle struct {
	client        *mongo.Client
	databaseCalls int
}

func (handle *serviceCoreContentMongoHandle) Ping(context.Context) error { return nil }
func (handle *serviceCoreContentMongoHandle) Disconnect(ctx context.Context) error {
	return handle.client.Disconnect(ctx)
}
func (handle *serviceCoreContentMongoHandle) Database(name string) *mongo.Database {
	handle.databaseCalls++
	return handle.client.Database(name)
}

type serviceCoreContentConfig struct {
	servicekit.BaseConfig `yaml:",inline"`
	Mongo                 struct {
		servicekit.MongoConfig `yaml:",inline"`
		Collection             string `yaml:"collection" required:"true"`
	} `yaml:"mongo"`
}

func prepareServiceCoreContentMongoFixture(t *testing.T) *serviceCoreContentMongoHandle {
	t.Helper()
	t.Setenv("APP_ENV", "alpha")
	t.Setenv("CONFIG_VERSION", "sha256:content")
	t.Setenv("SERVICE_CORE_CONTENT_SERVICE_CONFIG_VERSION", "sha256:content")
	t.Setenv("IMAGE_VERSION", "sha256:"+strings.Repeat("2", 64))
	t.Setenv("AUTH_JWT_SECRET", strings.Repeat("s", 64))
	t.Setenv("AUTH_JWT_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-app")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
	t.Setenv("AUTH_DEVICE_TICKET_SECRET", strings.Repeat("d", 64))
	t.Setenv("AUTH_DEVICE_TICKET_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_DEVICE_TICKET_AUDIENCE", "quwoquan-device")
	t.Setenv("AUTH_DEVICE_TICKET_TOKEN_VERSION", "1")
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "content-service.yaml"), []byte(strings.Join([]string{
		"config:",
		"  version: sha256:content",
		"service:",
		"  http:",
		"    addr: :0",
		"user_account_security_authority: {}",
		"mongo:",
		"  uri: mongodb://content-mongo.invalid:27017",
		"  database: quwoquan_content",
		"  collection: posts",
		"",
	}, "\n")), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CONFIG_ROOT", root)
	client, err := mongo.Connect(options.Client().ApplyURI("mongodb://content-mongo.invalid:27017"))
	if err != nil {
		t.Fatal(err)
	}
	return &serviceCoreContentMongoHandle{client: client}
}

func newServiceCoreContentMongoModule(
	handle *serviceCoreContentMongoHandle,
	ensureIndexes func(context.Context, *mongo.Database) error,
) (*servicekit.Module, error) {
	return servicekit.Bootstrap("content-service", servicekit.BootstrapSpec[serviceCoreContentConfig]{
		OperationDescriptors: []rtauth.OperationSecurityDescriptor{{
			CanonicalOperationID: "content.post.GetPost",
			ContractGraphSHA256:  strings.Repeat("a", 64),
			Transport:            "http",
			Method:               http.MethodGet,
			PathTemplate:         "/posts/{postId}",
			OperationKind:        "query",
			TimeoutMilliseconds:  1000,
		}},
		SkipAccountSecurityAuthority: true,
		MongoConnect: func(context.Context, servicekit.MongoConnectConfig) (servicekit.MongoHandle, error) {
			return handle, nil
		},
		Assemble: func(asm *servicekit.Assembly, _ *serviceCoreContentConfig) error {
			if asm.MongoDB == nil {
				return errors.New("content domain received nil canonical MongoDB")
			}
			return ensureIndexes(asm.Context, asm.MongoDB)
		},
	})
}

func TestContentMongoLifecycleMatchesServiceCoreAndStandalone(t *testing.T) {
	t.Run("service-core propagates index construction error", func(t *testing.T) {
		handle := prepareServiceCoreContentMongoFixture(t)
		indexErr := errors.New("query publication indexes unavailable")
		ensureCalls := 0
		t.Setenv("SERVICE_CORE_MODE", "1")
		factory := moduleFactory("content-service", func() (*servicekit.Module, error) {
			return newServiceCoreContentMongoModule(handle, func(_ context.Context, db *mongo.Database) error {
				ensureCalls++
				if db == nil {
					t.Fatal("EnsureIndexes received nil database")
				}
				return indexErr
			})
		})
		_, err := factory.New()
		if !errors.Is(err, indexErr) {
			t.Fatalf("service-core must propagate EnsureIndexes error, got %v", err)
		}
		if ensureCalls != 1 || handle.databaseCalls != 1 {
			t.Fatalf("calls: EnsureIndexes=%d Database=%d, want 1/1", ensureCalls, handle.databaseCalls)
		}
	})

	t.Run("standalone uses the same pre-domain database", func(t *testing.T) {
		handle := prepareServiceCoreContentMongoFixture(t)
		t.Setenv("SERVICE_CORE_MODE", "")
		ensureCalls := 0
		module, err := newServiceCoreContentMongoModule(handle, func(_ context.Context, db *mongo.Database) error {
			ensureCalls++
			if db == nil {
				t.Fatal("EnsureIndexes received nil database")
			}
			return nil
		})
		if err != nil {
			t.Fatalf("standalone construction error: %v", err)
		}
		if ensureCalls != 1 || handle.databaseCalls != 1 {
			t.Fatalf("calls: EnsureIndexes=%d Database=%d, want 1/1", ensureCalls, handle.databaseCalls)
		}
		if err := module.Shutdown(t.Context()); err != nil {
			t.Fatalf("standalone cleanup error: %v", err)
		}
	})
}

func TestCanonicalCompositionHasStableModulesAndEndpoints(t *testing.T) {
	t.Parallel()

	factories, endpoints, err := canonicalCompositionInputs()
	if err != nil {
		t.Fatalf("canonicalCompositionInputs() error = %v", err)
	}
	if len(factories) != 11 {
		t.Fatalf("factory count = %d, want 11", len(factories))
	}
	if len(endpoints) != len(factories) {
		t.Fatalf("endpoint count = %d, want %d", len(endpoints), len(factories))
	}
	names := make([]string, 0, len(factories))
	for index, factory := range factories {
		names = append(names, factory.Name)
		if endpoints[index].Module != factory.Name {
			t.Fatalf(
				"endpoint[%d].Module = %q, want %q",
				index,
				endpoints[index].Module,
				factory.Name,
			)
		}
	}
	want := []string{
		"user-service",
		"integration-service",
		"notification-service",
		"entity-service",
		"tag-service",
		"search-service",
		"content-service",
		"circle-service",
		"chat-service",
		"assistant-service",
		"api-edge",
	}
	if !reflect.DeepEqual(names, want) {
		t.Fatalf("module order = %v, want %v", names, want)
	}
	composition, err := servicehost.NewCompositionWithEndpoints(
		compositionProfile,
		endpoints,
		factories...,
	)
	if err != nil {
		t.Fatalf("NewCompositionWithEndpoints() error = %v", err)
	}
	const wantDigest = "sha256:9d0c452d38f17f89c509a0036c4f76197a9ba82a9151138cac85de292ce2c918"
	if got := composition.Identity().CompositionDigest; got != wantDigest {
		t.Fatalf("CompositionDigest = %q, want %q", got, wantDigest)
	}
}

func TestPrepareVirtualHTTPRoutingOverridesStandaloneAddress(t *testing.T) {
	t.Setenv("USER_SERVICE_ADDR", ":18081")
	t.Setenv(entityAccountSecurityAuthorityBaseURLEnvKey, "")

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		t.Fatalf("prepareVirtualHTTPRouting() error = %v", err)
	}
	defer router.Shutdown(t.Context())
	if got := os.Getenv("USER_SERVICE_ADDR"); got != "127.0.0.1:28081" {
		t.Fatalf("USER_SERVICE_ADDR = %q, want hidden listener", got)
	}
	if got := os.Getenv(entityAccountSecurityAuthorityBaseURLEnvKey); got != "http://127.0.0.1:28081" {
		t.Fatalf(
			"%s = %q, want service-core user authority",
			entityAccountSecurityAuthorityBaseURLEnvKey,
			got,
		)
	}
}

func TestPrepareVirtualHTTPRoutingProjectsEveryLogicalServiceBaseURL(t *testing.T) {
	manifest, err := loadCompositionManifest()
	if err != nil {
		t.Fatalf("loadCompositionManifest() error = %v", err)
	}
	for _, module := range manifest.Modules {
		t.Setenv(servicekit.ServiceBaseURLKey(module.Name), "")
	}

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		t.Fatalf("prepareVirtualHTTPRouting() error = %v", err)
	}
	defer router.Shutdown(t.Context())

	for _, module := range manifest.Modules {
		key := servicekit.ServiceBaseURLKey(module.Name)
		want := fmt.Sprintf("http://%s:%d", module.Host, module.Port)
		if got := os.Getenv(key); got != want {
			t.Errorf("%s = %q, want %q", key, got, want)
		}
	}
}

func TestRunPreflightProjectsTopologyBeforeModuleConstruction(t *testing.T) {
	t.Setenv("SERVICE_CORE_CONTENT_SERVICE_CONFIG_VERSION", "sha256:content")
	for _, serviceName := range []string{"user-service", "search-service", "entity-service"} {
		t.Setenv(servicekit.ServiceBaseURLKey(serviceName), "")
	}

	constructed := false
	composition, err := servicehost.NewComposition(
		"service-core-content-construction",
		moduleFactory("content-service", func() (*preflightTestModule, error) {
			identity, err := servicekit.ResolveIdentity("content-service")
			if err != nil {
				return nil, err
			}
			for _, serviceName := range []string{"user-service", "search-service", "entity-service"} {
				want := "http://" + serviceName
				if got := identity.ServiceBaseURL(serviceName); !strings.HasPrefix(got, want+":") {
					return nil, fmt.Errorf("%s base URL = %q, want canonical service-core origin", serviceName, got)
				}
			}
			constructed = true
			return &preflightTestModule{name: "content-service"}, nil
		}),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := runPreflight(composition); err != nil {
		t.Fatalf("runPreflight() error = %v", err)
	}
	if !constructed {
		t.Fatal("content-service constructor was not called")
	}
}

func TestPrepareVirtualHTTPRoutingSealsHiddenListeners(t *testing.T) {
	for _, key := range []string{
		"USER_SERVICE_ADDR",
		"CHAT_SERVICE_ADDR",
		"ASSISTANT_SERVICE_ADDR",
		"NOTIFICATION_SERVICE_ADDR",
	} {
		t.Setenv(key, "")
	}

	router, err := prepareVirtualHTTPRouting()
	if err != nil {
		t.Fatalf("prepareVirtualHTTPRouting() error = %v", err)
	}
	if router == nil {
		t.Fatal("prepareVirtualHTTPRouting() router = nil")
	}
	if got := os.Getenv("USER_SERVICE_ADDR"); got != "127.0.0.1:28081" {
		t.Fatalf("USER_SERVICE_ADDR = %q, want hidden listener", got)
	}
}

type preflightTestModule struct {
	name      string
	validated bool
	migrated  bool
	bound     bool
}

func (module *preflightTestModule) Name() string         { return module.name }
func (module *preflightTestModule) ConfigDigest() string { return "sha256:test" }
func (module *preflightTestModule) ValidateConfig(context.Context) error {
	module.validated = true
	return nil
}
func (module *preflightTestModule) PrepareMigration(context.Context) error {
	if !module.validated {
		return errors.New("migration ran before validation")
	}
	module.migrated = true
	return nil
}
func (module *preflightTestModule) Bind(context.Context) error {
	module.bound = true
	return errors.New("preflight must not bind")
}
func (module *preflightTestModule) Start(context.Context) error         { return nil }
func (module *preflightTestModule) Ready(context.Context) error         { return nil }
func (module *preflightTestModule) OpenAdmission(context.Context) error { return nil }
func (module *preflightTestModule) Shutdown(context.Context) error      { return nil }

func TestRunPreflightValidatesAndMigratesWithoutBindingListeners(t *testing.T) {
	module := &preflightTestModule{name: "assistant-service"}
	composition, err := servicehost.NewComposition(
		"service-core-preflight",
		servicehost.ModuleFactory{
			Name: module.name,
			New:  func() (servicehost.Module, error) { return module, nil },
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := runPreflight(composition); err != nil {
		t.Fatalf("runPreflight() error = %v", err)
	}
	if !module.validated || !module.migrated {
		t.Fatalf("preflight did not validate and migrate: %#v", module)
	}
	if module.bound {
		t.Fatal("preflight bound a listener")
	}
}

func TestApplyModuleEnvironmentScopesSharedProcessConfiguration(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "1")
	t.Setenv("SERVICE_NAME", "service-core")
	t.Setenv("CONFIG_VERSION", "sha256:aggregate")
	t.Setenv(
		"SERVICE_CORE_SEARCH_SERVICE_CONFIG_VERSION",
		"sha256:search",
	)
	t.Setenv(
		"SERVICE_CORE_SEARCH_SERVICE_SERVICE_INSTANCE_ID",
		"search-service-core-1",
	)

	restore, err := applyModuleEnvironment("search-service")
	if err != nil {
		t.Fatalf("applyModuleEnvironment() error = %v", err)
	}
	if got := os.Getenv("SERVICE_NAME"); got != "search-service" {
		t.Fatalf("SERVICE_NAME = %q, want search-service", got)
	}
	if got := os.Getenv("CONFIG_VERSION"); got != "sha256:search" {
		t.Fatalf("CONFIG_VERSION = %q, want search digest", got)
	}
	if got := os.Getenv("SERVICE_INSTANCE_ID"); got != "search-service-core-1" {
		t.Fatalf("SERVICE_INSTANCE_ID = %q, want module instance", got)
	}
	restore()
	if got := os.Getenv("SERVICE_NAME"); got != "service-core" {
		t.Fatalf("restored SERVICE_NAME = %q, want service-core", got)
	}
	if got := os.Getenv("CONFIG_VERSION"); got != "sha256:aggregate" {
		t.Fatalf("restored CONFIG_VERSION = %q, want aggregate digest", got)
	}
}

func TestApplyModuleEnvironmentFailsWithoutModuleConfig(t *testing.T) {
	t.Setenv("SERVICE_CORE_MODE", "1")
	t.Setenv("CONFIG_VERSION", "")
	t.Setenv("SERVICE_CORE_SEARCH_SERVICE_CONFIG_VERSION", "")

	if _, err := applyModuleEnvironment("search-service"); err == nil {
		t.Fatal("applyModuleEnvironment() error = nil, want missing config error")
	}
}
