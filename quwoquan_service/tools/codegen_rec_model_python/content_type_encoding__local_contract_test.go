package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

// spec_ref: specs/feature-tree/recommendation-platform/rec-model-training/training-pipeline/spec.md#gwt-001
func encodingSource(t *testing.T, field, values string) *contractcodegen.Source {
	t.Helper()
	root := t.TempDir()
	paths := []string{"owner/fields.yaml", "_shared/types.yaml"}
	writeEnumFixtureFile(t, filepath.Join(root, paths[0]), []byte("types:\n  CandidateInput:\n    fields:\n"+field))
	writeEnumFixtureFile(t, filepath.Join(root, paths[1]), []byte("enums:\n  ContentType: "+values+"\n"))
	source, err := contractcodegen.NewDocumentSource(root, paths)
	if err != nil {
		t.Fatal(err)
	}
	return source
}

const validEncodingField = "      - {name: contentType, type: enum, enum_ref: ContentType, model_encoding: {image: 0, video: 1, article: 2}}\n"

// spec_ref: specs/feature-tree/recommendation-platform/rec-model-training/training-pipeline/spec.md#gwt-001
func TestContentTypeEncodingStableAndFailClosed(t *testing.T) {
	first, err := renderContentTypeEncoding(encodingSource(t, validEncodingField, "[image, video, article]"), "owner")
	if err != nil {
		t.Fatal(err)
	}
	second, err := renderContentTypeEncoding(encodingSource(t, validEncodingField, "[article, image, video]"), "owner")
	if err != nil || first != second {
		t.Fatal("enum order changed model coordinates", err)
	}
	for _, bad := range []string{
		strings.Replace(validEncodingField, "enum_ref: ContentType, ", "", 1),
		strings.Replace(validEncodingField, "type: enum", "type: string", 1),
		strings.Replace(validEncodingField, ", article: 2", "", 1),
		strings.Replace(validEncodingField, "article: 2", "micro: 2", 1),
		strings.Replace(validEncodingField, "article: 2", "article: 1", 1),
		strings.Replace(validEncodingField, "article: 2", "article: -1", 1),
		strings.Replace(validEncodingField, "article: 2", "article: 3", 1),
		strings.Replace(validEncodingField, "article: 2", "article: true", 1),
		strings.Replace(validEncodingField, "article: 2", "article: 2.5", 1),
		strings.Replace(validEncodingField, "article: 2", "article: '2'", 1),
		strings.Replace(validEncodingField, "model_encoding", "model_encodng", 1),
	} {
		if _, err := renderContentTypeEncoding(encodingSource(t, bad, "[image, video, article]"), "owner"); err == nil {
			t.Fatalf("accepted invalid field: %s", bad)
		}
	}
	for _, values := range []string{"[image, video]", "[image, video, article, micro]", "[image, image, article]", "[]"} {
		if _, err := renderContentTypeEncoding(encodingSource(t, validEncodingField, values), "owner"); err == nil {
			t.Fatalf("accepted enum drift: %s", values)
		}
	}
}

// spec_ref: specs/feature-tree/recommendation-platform/rec-model-training/training-pipeline/spec.md#gwt-001
func TestContentTypeEncodingCanonicalConsumerParity(t *testing.T) {
	root := filepath.Join("..", "..")
	owner := "recommendation/recommendation/recommendation_model_release"
	contractRoot := filepath.Join(root, "services", "recommendation-service", "contracts")
	tmp := t.TempDir()
	fields, err := os.ReadFile(filepath.Join(contractRoot, "recommendation", "recommendation_model_release", "fields.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	shared, err := os.ReadFile(filepath.Join(root, "contracts", "metadata", "_shared", "types.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	writeEnumFixtureFile(t, filepath.Join(tmp, owner, "fields.yaml"), fields)
	writeEnumFixtureFile(t, filepath.Join(tmp, "_shared", "types.yaml"), shared)
	source, err := contractcodegen.NewDocumentSource(tmp, []string{owner + "/fields.yaml", "_shared/types.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	out := filepath.Join(tmp, "generated", "recommendation", "recommendation_model_release")
	if err := writeContentTypeEncoding(source, owner, out); err != nil {
		t.Fatal(err)
	}
	module := filepath.Join(out, "content_type_encoding.py")
	service, err := filepath.Abs(filepath.Join(root, "services", "recommendation-service"))
	if err != nil {
		t.Fatal(err)
	}
	// 只执行现有纯提取器与当前临时生成物；不导入训练依赖，不连接数据库，不训练模型。
	cmd := exec.Command("python3", "-B", "-c", `import ast, runpy, sys
from pathlib import Path
module, service = sys.argv[1:]
encoding = runpy.run_path(module)['CONTENT_TYPE_MAP']
assert dict(encoding) == {'image': 0, 'video': 1, 'article': 2}
try:
    encoding['image'] = 7
except TypeError:
    pass
else:
    raise AssertionError('encoding is mutable')
runtime = Path(service) / 'internal/recommendation/recommendation_model_release/infrastructure/model_runtime'
sys.path[:0] = [service, str(runtime)]
test = Path(service) / 'tests/local_contract/recommendation/recommendation_model_release/model_contract/test_intersection_features__feature_vector__contract__local_contract_test.py'
sys.path.insert(0, str(Path(service) / 'tests'))
# 显式装载临时生成模块，保持消费者正常 import 路径，不写真实 generated。
import importlib.util
name = 'generated.recommendation.recommendation_model_release.content_type_encoding'
spec = importlib.util.spec_from_file_location(name, module)
m = importlib.util.module_from_spec(spec)
sys.modules[name] = m
spec.loader.exec_module(m)
namespace = runpy.run_path(str(test))
for value, code in encoding.items():
    namespace['test_content_type_encoding_is_stable_across_serving_and_training'](value, code)
for value in ['micro', 'moment', 'photo', 'homepage', 'unknown', '', None]:
    namespace['test_retired_or_unknown_content_type_is_not_an_encodable_category'](value)
for model in [None, object()]:
    namespace['test_scorer_rejects_retired_type_before_model_or_rule_fallback'](model)
namespace['test_serving_and_training_vectors_are_isomorphic_for_matched_edge']()
namespace['test_all_content_type_consumers_import_generated_encoding']()
`, module, service)
	cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("temporary generated parity: %v\n%s", err, output)
	}
}
