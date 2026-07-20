package http

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// 手写 mux 防漂移：metadata 声明的每个 circle 域 path_template 必须能在
// CircleHandler 的路由源码中找到对应分支；新增 operation 却未接线时本测试红。
func TestCircleHandlerRoutesCoverMetadataPathTemplates(t *testing.T) {
	root := repositoryRoot(t)
	handlerSource := readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/circle_handler.go")) +
		readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/circle_membership_handler.go")) +
		readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/circle_file_handler.go")) +
		readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/circle_group_handler.go")) +
		readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/circle_group_membership_handler.go")) +
		readFile(t, filepath.Join(root, "services/circle-service/internal/adapters/http/post_placement_handler.go"))

	metadataDir := filepath.Join(root, "contracts/metadata/social")
	subResources := map[string]struct{}{}
	topLevel := map[string]struct{}{}
	for _, object := range []string{
		"circle", "circle_membership", "circle_group", "circle_group_membership",
		"circle_file", "circle_post_placement", "circle_behavior_fact",
	} {
		document := struct {
			APIRoutes []struct {
				Path string `yaml:"path"`
			} `yaml:"api_routes"`
		}{}
		payload := readFile(t, filepath.Join(metadataDir, object, "service.yaml"))
		if err := yaml.Unmarshal([]byte(payload), &document); err != nil {
			t.Fatalf("parse %s service.yaml: %v", object, err)
		}
		for _, route := range document.APIRoutes {
			path := strings.TrimSpace(route.Path)
			switch {
			case strings.HasPrefix(path, "/circles/{circleId}/"):
				rest := strings.TrimPrefix(path, "/circles/{circleId}/")
				subResources[strings.SplitN(rest, "/", 2)[0]] = struct{}{}
			case strings.HasPrefix(path, "/personas/"):
				topLevel["/personas/"] = struct{}{}
			case path == "/circles" || strings.HasPrefix(path, "/circles/"):
				topLevel["/circles"] = struct{}{}
			default:
				t.Fatalf("unexpected circle path template outside handler scope: %s", path)
			}
		}
	}

	for prefix := range topLevel {
		if !strings.Contains(handlerSource, `"`+prefix+`"`) {
			t.Fatalf("handler mux missing top-level route %q", prefix)
		}
	}
	caseExpr := regexp.MustCompile(`case "([a-z-]+)"`)
	handled := map[string]struct{}{}
	for _, match := range caseExpr.FindAllStringSubmatch(handlerSource, -1) {
		handled[match[1]] = struct{}{}
	}
	for sub := range subResources {
		if _, ok := handled[sub]; !ok {
			t.Fatalf("handler switch missing metadata sub-resource %q", sub)
		}
	}
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("go.mod not found above test directory")
		}
		dir = parent
	}
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(payload)
}
