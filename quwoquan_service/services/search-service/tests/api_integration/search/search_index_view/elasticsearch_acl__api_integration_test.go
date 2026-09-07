// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/design.md#dec-002
package api_integration

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"

	"quwoquan_service/runtime/search/es"
)

const (
	elasticsearchCJKSecurityImage = "quwoquan/elasticsearch-cjk:8.13.4"
	elasticsearchOfficialImage    = "docker.elastic.co/elasticsearch/elasticsearch:8.13.4"
)

type elasticsearchCredentials struct {
	username string
	password string
	apiKey   string
}

type elasticsearchHTTP struct {
	endpoint    string
	credentials elasticsearchCredentials
	client      *http.Client
}

type elasticsearchResponse struct {
	status int
	body   []byte
}

type elasticsearchIndexPrivilege struct {
	Names      []string `json:"names"`
	Privileges []string `json:"privileges"`
}

type elasticsearchRoleDescriptor struct {
	Cluster []string                      `json:"cluster"`
	Indices []elasticsearchIndexPrivilege `json:"indices"`
}

type elasticsearchAPIKey struct {
	id      string
	encoded string
}

type secureElasticsearch struct {
	endpoint string
	password string
	image    string
	stop     func()
}

// TestElasticsearchRoleACL proves the deployment binding roles against the
// real Elasticsearch authorization engine. httptest/fakes cannot prove these
// index-pattern and action-level denials, so Docker absence is a hard failure.
func TestElasticsearchRoleACL(t *testing.T) {
	cluster := startSecureElasticsearch(t)
	t.Cleanup(cluster.stop)
	t.Logf("secured Elasticsearch image: %s", cluster.image)

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	superuser := elasticsearchHTTP{
		endpoint: cluster.endpoint,
		credentials: elasticsearchCredentials{
			username: "elastic",
			password: cluster.password,
		},
		client: &http.Client{Timeout: 30 * time.Second},
	}

	suffix := randomHex(t, 6)
	searchAlias := "quwoquan-objects-acl-" + suffix
	searchWriteAlias := searchAlias + "-write"
	searchIndex := searchAlias + "-v1"
	searchTemplate := searchAlias + "-template"
	telemetryIndex := "app-product-telemetry-acl-" + suffix
	startupIndex := "app-startup-diagnostic-acl-" + suffix
	runtimeIndex := "runtime-diagnostics-acl-" + suffix

	roles := map[string]elasticsearchRoleDescriptor{
		// The search patterns intentionally include the read alias, write alias,
		// and versioned physical indices in one generated namespace.
		"search-reader-" + suffix: {
			Indices: []elasticsearchIndexPrivilege{{
				Names:      []string{searchAlias + "*"},
				Privileges: []string{"read", "view_index_metadata"},
			}},
		},
		"search-writer-" + suffix: {
			Indices: []elasticsearchIndexPrivilege{{
				Names:      []string{searchAlias + "*"},
				Privileges: []string{"write"},
			}},
		},
		"search-admin-" + suffix: {
			Cluster: []string{"manage_index_templates"},
			Indices: []elasticsearchIndexPrivilege{{
				Names:      []string{searchAlias + "*"},
				Privileges: []string{"manage"},
			}},
		},
		"product-telemetry-" + suffix: {
			Indices: []elasticsearchIndexPrivilege{{
				Names: []string{
					"app-product-telemetry-*",
					"app-startup-diagnostic-*",
				},
				Privileges: []string{"read", "write"},
			}},
		},
		"runtime-logs-" + suffix: {
			Indices: []elasticsearchIndexPrivilege{{
				Names:      []string{"runtime-diagnostics-*"},
				Privileges: []string{"read", "write"},
			}},
		},
	}

	roleNames := make([]string, 0, len(roles))
	apiKeyIDs := make([]string, 0, len(roles))
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if len(apiKeyIDs) > 0 {
			response, err := superuser.do(cleanupCtx, http.MethodDelete, "/_security/api_key", map[string]any{"ids": apiKeyIDs})
			if err != nil {
				t.Errorf("invalidate Elasticsearch API keys: %v", err)
			} else if response.status != http.StatusOK {
				t.Errorf("invalidate Elasticsearch API keys: HTTP %d", response.status)
			}
		}
		for _, roleName := range roleNames {
			response, err := superuser.do(cleanupCtx, http.MethodDelete, "/_security/role/"+roleName, nil)
			if err != nil {
				t.Errorf("delete Elasticsearch role %s: %v", roleName, err)
			} else if response.status != http.StatusOK && response.status != http.StatusNotFound {
				t.Errorf("delete Elasticsearch role %s: HTTP %d", roleName, response.status)
			}
		}
		for _, path := range []string{
			"/" + searchIndex,
			"/" + telemetryIndex,
			"/" + startupIndex,
			"/" + runtimeIndex,
			"/_index_template/" + searchTemplate,
		} {
			response, err := superuser.do(cleanupCtx, http.MethodDelete, path, nil)
			if err != nil {
				t.Errorf("delete Elasticsearch ACL resource %s: %v", path, err)
			} else if response.status != http.StatusOK && response.status != http.StatusNotFound {
				t.Errorf("delete Elasticsearch ACL resource %s: HTTP %d", path, response.status)
			}
		}
	})

	keys := make(map[string]elasticsearchAPIKey, len(roles))
	for roleName, descriptor := range roles {
		assertElasticsearchStatus(t, superuser, ctx, http.MethodPut, "/_security/role/"+roleName, descriptor, http.StatusOK)
		roleNames = append(roleNames, roleName)
		key := createElasticsearchAPIKey(t, superuser, ctx, roleName, descriptor)
		keys[roleName] = key
		apiKeyIDs = append(apiKeyIDs, key.id)
	}

	readerRole := "search-reader-" + suffix
	writerRole := "search-writer-" + suffix
	adminRole := "search-admin-" + suffix
	telemetryRole := "product-telemetry-" + suffix
	runtimeRole := "runtime-logs-" + suffix
	readerHTTP := apiKeyElasticsearchHTTP(cluster.endpoint, keys[readerRole].encoded)
	writerHTTP := apiKeyElasticsearchHTTP(cluster.endpoint, keys[writerRole].encoded)
	adminHTTP := apiKeyElasticsearchHTTP(cluster.endpoint, keys[adminRole].encoded)
	telemetryHTTP := apiKeyElasticsearchHTTP(cluster.endpoint, keys[telemetryRole].encoded)
	runtimeHTTP := apiKeyElasticsearchHTTP(cluster.endpoint, keys[runtimeRole].encoded)

	t.Run("deployment admin manages only the search namespace", func(t *testing.T) {
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/_index_template/"+searchTemplate, map[string]any{
			"index_patterns": []string{searchAlias + "-*"},
			"priority":       100,
			"template": map[string]any{
				"settings": map[string]any{
					"number_of_shards":   1,
					"number_of_replicas": 0,
				},
			},
		}, http.StatusOK)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+searchIndex, map[string]any{
			"mappings": map[string]any{
				"properties": map[string]any{
					"objectType":    map[string]any{"type": "keyword"},
					"objectId":      map[string]any{"type": "keyword"},
					"title":         map[string]any{"type": "text"},
					"target":        map[string]any{"type": "keyword"},
					"visibility":    map[string]any{"type": "keyword"},
					"sourceVersion": map[string]any{"type": "long"},
					"deleted":       map[string]any{"type": "boolean"},
				},
			},
			"aliases": map[string]any{
				searchAlias:      map[string]any{},
				searchWriteAlias: map[string]any{"is_write_index": true},
			},
		}, http.StatusOK)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/_aliases", map[string]any{
			"actions": []any{
				map[string]any{"add": map[string]any{
					"index": searchIndex,
					"alias": searchAlias + "-admin-probe",
				}},
			},
		}, http.StatusOK)

		// manage_index_templates is an Elasticsearch cluster privilege and cannot
		// be name-scoped; index-level manage remains constrained to Search.
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+telemetryIndex, map[string]any{}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+runtimeIndex, map[string]any{}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/"+searchAlias+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+searchWriteAlias+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
	})

	readerClient := newACLSearchClient(t, cluster.endpoint, keys[readerRole].encoded, searchAlias)
	writerClient := newACLSearchClient(t, cluster.endpoint, keys[writerRole].encoded, searchAlias)
	documentID := "content.post:acl-" + suffix
	document := map[string]any{
		"objectType": "content.post",
		"objectId":   "acl-" + suffix,
		"title":      "真实 Elasticsearch ACL",
		"target":     "article",
		"visibility": "public",
	}

	t.Run("writer can versioned upsert and tombstone but cannot read or administer", func(t *testing.T) {
		applied, err := writerClient.UpsertVersioned(ctx, searchWriteAlias, documentID, 1, document)
		if err != nil || !applied {
			t.Fatalf("writer versioned upsert applied=%v err=%v", applied, err)
		}
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/"+searchIndex+"/_refresh", nil, http.StatusOK)

		_, err = writerClient.Search(ctx, searchAlias, map[string]any{"query": map[string]any{"match_all": map[string]any{}}})
		assertClientHTTPForbidden(t, "writer search", err)
		_, err = writerClient.OpenPIT(ctx)
		assertClientHTTPForbidden(t, "writer PIT", err)
		assertElasticsearchStatus(t, writerHTTP, ctx, http.MethodPost, "/_aliases", map[string]any{
			"actions": []any{map[string]any{"add": map[string]any{
				"index": searchIndex,
				"alias": searchAlias + "-writer-forbidden",
			}}},
		}, http.StatusForbidden)
		assertElasticsearchStatus(t, writerHTTP, ctx, http.MethodPut, "/"+searchAlias+"-writer-forbidden-index", map[string]any{}, http.StatusForbidden)
	})

	t.Run("reader can search and PIT but cannot write or administer", func(t *testing.T) {
		candidates, err := readerClient.Search(ctx, searchAlias, map[string]any{
			"query": map[string]any{"match_all": map[string]any{}},
		})
		if err != nil {
			t.Fatalf("reader search: %v", err)
		}
		if len(candidates) != 1 || candidates[0].Document.ObjectID != "acl-"+suffix {
			t.Fatalf("reader search candidates=%#v", candidates)
		}
		pitID, err := readerClient.OpenPIT(ctx)
		if err != nil {
			t.Fatalf("reader open PIT: %v", err)
		}
		if err := readerClient.ClosePIT(ctx, pitID); err != nil {
			t.Fatalf("reader close PIT: %v", err)
		}

		_, err = readerClient.UpsertVersioned(ctx, searchWriteAlias, documentID, 2, document)
		assertVersionedWriteForbidden(t, "reader external-version upsert", err)
		_, err = readerClient.TombstoneVersioned(ctx, searchWriteAlias, documentID, "content.post", "acl-"+suffix, 2)
		assertVersionedWriteForbidden(t, "reader tombstone", err)
		assertElasticsearchStatus(t, readerHTTP, ctx, http.MethodPost, "/_aliases", map[string]any{
			"actions": []any{map[string]any{"add": map[string]any{
				"index": searchIndex,
				"alias": searchAlias + "-reader-forbidden",
			}}},
		}, http.StatusForbidden)
		assertElasticsearchStatus(t, readerHTTP, ctx, http.MethodPut, "/"+searchAlias+"-reader-forbidden-index", map[string]any{}, http.StatusForbidden)
	})

	t.Run("writer tombstone remains allowed", func(t *testing.T) {
		applied, err := writerClient.TombstoneVersioned(
			ctx,
			searchWriteAlias,
			documentID,
			"content.post",
			"acl-"+suffix,
			2,
		)
		if err != nil || !applied {
			t.Fatalf("writer versioned tombstone applied=%v err=%v", applied, err)
		}
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/"+searchIndex+"/_refresh", nil, http.StatusOK)
		candidates, err := readerClient.Search(ctx, searchAlias, map[string]any{
			"query": map[string]any{"match_all": map[string]any{}},
		})
		if err != nil {
			t.Fatalf("reader search after tombstone: %v", err)
		}
		if len(candidates) != 0 {
			t.Fatalf("reader saw tombstoned candidates=%#v", candidates)
		}
	})

	for _, index := range []string{telemetryIndex, startupIndex, runtimeIndex} {
		assertElasticsearchStatus(t, superuser, ctx, http.MethodPut, "/"+index, map[string]any{
			"settings": map[string]any{"number_of_replicas": 0},
		}, http.StatusOK)
	}

	t.Run("product telemetry is confined to product and startup indices", func(t *testing.T) {
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPut, "/"+telemetryIndex+"/_doc/product", map[string]any{"kind": "product"}, http.StatusCreated)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPut, "/"+startupIndex+"/_doc/startup", map[string]any{"kind": "startup"}, http.StatusCreated)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPost, "/"+telemetryIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusOK)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPost, "/"+startupIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusOK)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPost, "/"+runtimeIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPut, "/"+runtimeIndex+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPost, "/"+searchAlias+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, telemetryHTTP, ctx, http.MethodPut, "/"+searchWriteAlias+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
	})

	t.Run("runtime logs are confined to runtime diagnostic indices", func(t *testing.T) {
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPut, "/"+runtimeIndex+"/_doc/runtime", map[string]any{"kind": "runtime"}, http.StatusCreated)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPost, "/"+runtimeIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusOK)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPost, "/"+telemetryIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPost, "/"+startupIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPut, "/"+telemetryIndex+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPost, "/"+searchAlias+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, runtimeHTTP, ctx, http.MethodPut, "/"+searchWriteAlias+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
	})

	t.Run("all search credentials are namespace confined", func(t *testing.T) {
		assertElasticsearchStatus(t, readerHTTP, ctx, http.MethodPost, "/"+telemetryIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, readerHTTP, ctx, http.MethodPost, "/"+runtimeIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, writerHTTP, ctx, http.MethodPut, "/"+telemetryIndex+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
		assertElasticsearchStatus(t, writerHTTP, ctx, http.MethodPut, "/"+runtimeIndex+"/_doc/forbidden", map[string]any{"kind": "forbidden"}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+telemetryIndex+"/_settings", map[string]any{"index": map[string]any{"refresh_interval": "1s"}}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPut, "/"+runtimeIndex+"/_settings", map[string]any{"index": map[string]any{"refresh_interval": "1s"}}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/"+telemetryIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
		assertElasticsearchStatus(t, adminHTTP, ctx, http.MethodPost, "/"+runtimeIndex+"/_search", map[string]any{"query": map[string]any{"match_all": map[string]any{}}}, http.StatusForbidden)
	})
}

func startSecureElasticsearch(t *testing.T) secureElasticsearch {
	t.Helper()
	ensureElasticsearchDockerHost(t)
	password := "acl-" + randomHex(t, 24)
	images := []string{elasticsearchCJKSecurityImage, elasticsearchOfficialImage}
	failures := make([]string, 0, len(images))

	for _, image := range images {
		container, endpoint, err := startSecureElasticsearchContainer(t.Context(), image, password)
		if err != nil {
			failures = append(failures, image+": "+redactSecret(err.Error(), password))
			continue
		}
		securityErr := verifyElasticsearchSecurity(endpoint, password)
		if securityErr != nil {
			terminateCtx, cancel := context.WithTimeout(context.Background(), time.Minute)
			_ = container.Terminate(terminateCtx)
			cancel()
			failures = append(failures, image+": "+redactSecret(securityErr.Error(), password))
			continue
		}
		return secureElasticsearch{
			endpoint: endpoint,
			password: password,
			image:    image,
			stop: func() {
				terminateCtx, cancel := context.WithTimeout(context.Background(), time.Minute)
				defer cancel()
				if err := container.Terminate(terminateCtx); err != nil && !strings.Contains(err.Error(), "removal of container") {
					t.Errorf("terminate secured Elasticsearch: %v", err)
				}
			},
		}
	}

	t.Fatalf("GATE_BLOCK: no Elasticsearch 8.13.4 image started with real xpack security: %s", strings.Join(failures, "; "))
	return secureElasticsearch{}
}

func startSecureElasticsearchContainer(
	ctx context.Context,
	image string,
	password string,
) (container testcontainers.Container, endpoint string, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	environment := map[string]string{
		"discovery.type":                                    "single-node",
		"xpack.security.enabled":                            "true",
		"xpack.security.http.ssl.enabled":                   "false",
		"xpack.security.transport.ssl.enabled":              "false",
		"cluster.routing.allocation.disk.threshold_enabled": "false",
		"ELASTIC_PASSWORD":                                  password,
		"ES_JAVA_OPTS":                                      "-Xms512m -Xmx512m",
	}
	if runtime.GOARCH == "arm64" {
		environment["CLI_JAVA_OPTS"] = "-XX:UseSVE=0"
		environment["ES_JAVA_OPTS"] = "-XX:UseSVE=0 -Xms512m -Xmx512m"
	}
	container, err = testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        image,
			SkipReaper:   true,
			Env:          environment,
			ExposedPorts: []string{"9200/tcp"},
			WaitingFor: wait.ForHTTP("/_security/_authenticate").
				WithPort(nat.Port("9200/tcp")).
				WithBasicAuth("elastic", password).
				WithStatusCodeMatcher(func(status int) bool { return status == http.StatusOK }).
				WithStartupTimeout(4 * time.Minute),
		},
		Started: true,
	})
	if err != nil {
		if container != nil {
			terminateCtx, cancel := context.WithTimeout(context.Background(), time.Minute)
			_ = container.Terminate(terminateCtx)
			cancel()
		}
		return nil, "", err
	}
	endpoint, err = container.Endpoint(ctx, "http")
	if err != nil {
		terminateCtx, cancel := context.WithTimeout(context.Background(), time.Minute)
		_ = container.Terminate(terminateCtx)
		cancel()
		return nil, "", fmt.Errorf("resolve endpoint: %w", err)
	}
	return container, strings.TrimRight(endpoint, "/"), nil
}

func verifyElasticsearchSecurity(endpoint, password string) error {
	client := &http.Client{Timeout: 10 * time.Second}
	request, err := http.NewRequest(http.MethodGet, endpoint+"/", nil)
	if err != nil {
		return err
	}
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("unauthenticated security probe transport failure: %w", err)
	}
	_, _ = io.Copy(io.Discard, response.Body)
	_ = response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		return fmt.Errorf("xpack security inactive: unauthenticated request returned HTTP %d, want 401", response.StatusCode)
	}
	request, err = http.NewRequest(http.MethodGet, endpoint+"/", nil)
	if err != nil {
		return err
	}
	request.SetBasicAuth("elastic", password)
	response, err = client.Do(request)
	if err != nil {
		return fmt.Errorf("authenticated version probe transport failure: %w", err)
	}
	versionBody, readErr := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	_ = response.Body.Close()
	if readErr != nil {
		return fmt.Errorf("read Elasticsearch version probe: %w", readErr)
	}
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("authenticated version probe returned HTTP %d, want 200", response.StatusCode)
	}
	var root struct {
		Version struct {
			Number string `json:"number"`
		} `json:"version"`
	}
	if err := json.Unmarshal(versionBody, &root); err != nil || root.Version.Number != "8.13.4" {
		return fmt.Errorf("Elasticsearch version is %q, want 8.13.4", root.Version.Number)
	}
	request, err = http.NewRequest(http.MethodGet, endpoint+"/_security/_authenticate", nil)
	if err != nil {
		return err
	}
	request.SetBasicAuth("elastic", password)
	response, err = client.Do(request)
	if err != nil {
		return fmt.Errorf("authenticated security probe transport failure: %w", err)
	}
	_, _ = io.Copy(io.Discard, response.Body)
	_ = response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("superuser security probe returned HTTP %d, want 200", response.StatusCode)
	}
	return nil
}

func ensureElasticsearchDockerHost(t *testing.T) {
	t.Helper()
	t.Setenv("TESTCONTAINERS_RYUK_DISABLED", "true")
	if strings.TrimSpace(os.Getenv("DOCKER_HOST")) != "" {
		return
	}
	output, err := exec.Command("docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}").Output()
	if err != nil {
		t.Fatalf("GATE_BLOCK: real Elasticsearch ACL test requires Docker: %v", err)
	}
	dockerHost := strings.TrimSpace(string(output))
	if dockerHost == "" {
		t.Fatal("GATE_BLOCK: active Docker context has no endpoint")
	}
	t.Setenv("DOCKER_HOST", dockerHost)
}

func apiKeyElasticsearchHTTP(endpoint, apiKey string) elasticsearchHTTP {
	return elasticsearchHTTP{
		endpoint:    endpoint,
		credentials: elasticsearchCredentials{apiKey: apiKey},
		client:      &http.Client{Timeout: 30 * time.Second},
	}
}

func (client elasticsearchHTTP) do(
	ctx context.Context,
	method string,
	path string,
	body any,
) (elasticsearchResponse, error) {
	var payload io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return elasticsearchResponse{}, fmt.Errorf("marshal %s %s: %w", method, path, err)
		}
		payload = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, client.endpoint+path, payload)
	if err != nil {
		return elasticsearchResponse{}, fmt.Errorf("build %s %s: %w", method, path, err)
	}
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	switch {
	case client.credentials.apiKey != "":
		request.Header.Set("Authorization", "ApiKey "+client.credentials.apiKey)
	case client.credentials.username != "":
		request.SetBasicAuth(client.credentials.username, client.credentials.password)
	}
	response, err := client.client.Do(request)
	if err != nil {
		return elasticsearchResponse{}, fmt.Errorf("transport failure for %s %s: %w", method, path, err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return elasticsearchResponse{}, fmt.Errorf("read %s %s response: %w", method, path, err)
	}
	return elasticsearchResponse{status: response.StatusCode, body: responseBody}, nil
}

func assertElasticsearchStatus(
	t *testing.T,
	client elasticsearchHTTP,
	ctx context.Context,
	method string,
	path string,
	body any,
	want int,
) elasticsearchResponse {
	t.Helper()
	response, err := client.do(ctx, method, path, body)
	if err != nil {
		t.Fatalf("%s %s did not reach Elasticsearch: %v", method, path, err)
	}
	if response.status != want {
		t.Fatalf("%s %s returned HTTP %d, want %d", method, path, response.status, want)
	}
	return response
}

func createElasticsearchAPIKey(
	t *testing.T,
	superuser elasticsearchHTTP,
	ctx context.Context,
	roleName string,
	descriptor elasticsearchRoleDescriptor,
) elasticsearchAPIKey {
	t.Helper()
	response := assertElasticsearchStatus(t, superuser, ctx, http.MethodPost, "/_security/api_key", map[string]any{
		"name": roleName,
		"role_descriptors": map[string]any{
			roleName: descriptor,
		},
	}, http.StatusOK)
	var decoded struct {
		ID      string `json:"id"`
		Encoded string `json:"encoded"`
	}
	if err := json.Unmarshal(response.body, &decoded); err != nil {
		t.Fatalf("decode Elasticsearch API key response without logging secret: %v", err)
	}
	if decoded.ID == "" || decoded.Encoded == "" {
		t.Fatal("Elasticsearch API key response omitted id or encoded credential")
	}
	return elasticsearchAPIKey{id: decoded.ID, encoded: decoded.Encoded}
}

func newACLSearchClient(t *testing.T, endpoint, apiKey, index string) *es.Client {
	t.Helper()
	client, err := es.NewClient(es.Config{
		Endpoints:      []string{endpoint},
		APIKey:         apiKey,
		Index:          index,
		RequestTimeout: 30 * time.Second,
	})
	if err != nil {
		t.Fatalf("create production Elasticsearch client: %v", err)
	}
	return client
}

func assertVersionedWriteForbidden(t *testing.T, operation string, err error) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s unexpectedly succeeded", operation)
	}
	if !errors.Is(err, es.ErrVersionedWriteRejected) || !strings.Contains(err.Error(), "status 403") {
		t.Fatalf("%s must expose real HTTP 403 as a non-network rejection: %v", operation, err)
	}
	if es.IsDependencyUnavailable(err) {
		t.Fatalf("%s misclassified HTTP 403 as dependency/network failure: %v", operation, err)
	}
}

func assertClientHTTPForbidden(t *testing.T, operation string, err error) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s unexpectedly succeeded", operation)
	}
	if !strings.Contains(err.Error(), "status 403") {
		t.Fatalf("%s must expose real HTTP 403: %v", operation, err)
	}
	if es.IsDependencyUnavailable(err) {
		t.Fatalf("%s misclassified HTTP 403 as dependency/network failure: %v", operation, err)
	}
}

func randomHex(t *testing.T, bytesCount int) string {
	t.Helper()
	value := make([]byte, bytesCount)
	if _, err := rand.Read(value); err != nil {
		t.Fatalf("generate ephemeral Elasticsearch test secret: %v", err)
	}
	return hex.EncodeToString(value)
}

func redactSecret(message, secret string) string {
	if secret == "" {
		return message
	}
	return strings.ReplaceAll(message, secret, "[REDACTED]")
}
