// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-001
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestVideoCoverFieldsHaveDistinctCanonicalPresentationRoles(t *testing.T) {
	contractPath := filepath.Join(
		quwoquanServiceRoot(t),
		"services/content-service/contracts/content/post/projections/video_post.yaml",
	)
	raw, err := os.ReadFile(contractPath)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Fields []struct {
			Name        string `yaml:"name"`
			Description string `yaml:"description"`
		} `yaml:"fields"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", contractPath, err)
	}
	descriptions := make(map[string]string, 2)
	for _, field := range document.Fields {
		if field.Name == "thumbnailUrl" || field.Name == "coverUrl" {
			descriptions[field.Name] = field.Description
		}
	}
	thumbnailDescription := descriptions["thumbnailUrl"]
	coverDescription := descriptions["coverUrl"]
	if !strings.Contains(thumbnailDescription, "视频未播放态专属主封面") ||
		!strings.Contains(thumbnailDescription, "优先级高于通用 coverUrl") {
		t.Fatalf("thumbnailUrl role is not canonical: %q", thumbnailDescription)
	}
	if !strings.Contains(coverDescription, "跨内容类型的通用封面") ||
		!strings.Contains(coverDescription, "第二展示优先级") {
		t.Fatalf("coverUrl role is not canonical: %q", coverDescription)
	}
	for fieldName, description := range descriptions {
		if strings.Contains(description, "兼容") || strings.Contains(description, "旧卡片") {
			t.Fatalf("%s still teaches a compatibility track: %q", fieldName, description)
		}
	}
}
