package validate

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

// `channel` 是一个没有值域的字段：229 条事件写出 25 种取值，同时混装投递机制
// （`transactional_outbox`）、笔误（6 处 `outbox`）与 topic 名（`events.user.account` 等
// 12 种），另有 3 条连键都没有。拆成受控 `delivery_semantics` 与自由 `topic` 之后，值域
// 必须由 schema 直接强制——否则「取值收敛」只是换了个字段名继续失控。
//
// 这些负例正是**规则不再依赖子串匹配的前提**：只要 schema 挡不住 `channel` 回流或未知
// 取值，validate 侧的精确匹配就会重新变成「未知即豁免」。
func TestEventsSchemaEnforcesDeliverySemanticsValueDomain(t *testing.T) {
	t.Parallel()

	schema := compileEventsSchema(t)
	for name, expectation := range map[string]struct {
		event      map[string]any
		wantReject bool
	}{
		"受控取值通过": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "PostChanged",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
			},
		},
		"受控取值可带 topic": {
			event: map[string]any{
				"name": "UserSuspended", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "events.user.UserSuspended",
				"topic":           "events.user.account", "payload_entity": "UserAccount",
				"payload_fields": []any{"userId"},
			},
		},
		"outbox 缺 wire identity 被拒": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"payload_entity": "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"非 outbox 不得冒充 wire identity owner": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_event_log",
				"wire_event_type": "PostChanged",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"wire identity 禁止空白与路径字符": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "content/post changed",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"wire identity 禁止未出现于 production 的分隔符": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "content:post-changed",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"缺 delivery_semantics 被拒": {
			event: map[string]any{
				"name": "PostChanged", "payload_entity": "Post",
				"payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"笔误取值被拒": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "outbox",
				"payload_entity": "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
		"topic 名不得当作投递保证": {
			event: map[string]any{
				"name": "UserSuspended", "delivery_semantics": "events.user.account",
				"payload_entity": "UserAccount", "payload_fields": []any{"userId"},
			},
			wantReject: true,
		},
		"二义命名被拒": {
			event: map[string]any{
				"name": "PushDeliverySucceeded", "delivery_semantics": "callback_or_event",
				"payload_entity": "PushDelivery", "payload_fields": []any{"deliveryId"},
			},
			wantReject: true,
		},
		// 单轨：拆完就不留过渡态，`channel` 不得与新字段并存。
		"channel 回流被拒": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "PostChanged",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
				"channel": "transactional_outbox",
			},
			wantReject: true,
		},
		"producer-side consumers 回流被拒": {
			event: map[string]any{
				"name": "PostChanged", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "PostChanged",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
				"consumers": []any{"post-projector"},
			},
			wantReject: true,
		},
		"非 PascalCase 事件名被拒": {
			event: map[string]any{
				"name": "content.post.changed", "delivery_semantics": "transactional_outbox",
				"wire_event_type": "PostChanged",
				"payload_entity":  "Post", "payload_fields": []any{"postId"},
			},
			wantReject: true,
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			instance := map[string]any{"events": []any{expectation.event}}
			err := schema.Validate(instance)
			if expectation.wantReject && err == nil {
				t.Fatalf("events schema accepted %v, want rejection", expectation.event)
			}
			if !expectation.wantReject && err != nil {
				t.Fatalf("events schema rejected %v: %v", expectation.event, err)
			}
		})
	}
	if err := schema.Validate(map[string]any{
		"events": []any{map[string]any{
			"name": "PostChanged", "delivery_semantics": "transactional_outbox",
			"wire_event_type": "PostChanged",
			"payload_entity":  "Post", "payload_fields": []any{"postId"},
		}},
		"consumption": []any{},
	}); err == nil {
		t.Fatal("events schema accepted legacy top-level consumption")
	}
}

func TestAllObjectEventsMatchClosedSchema(t *testing.T) {
	t.Parallel()

	schema := compileEventsSchema(t)
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	servicesRoot := filepath.Join(
		filepath.Dir(thisFile), "..", "..", "..", "services",
	)
	count := 0
	err := filepath.WalkDir(servicesRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "events.yaml" ||
			!strings.Contains(filepath.ToSlash(path), "/contracts/") {
			return nil
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		var instance any
		if decodeErr := yaml.Unmarshal(data, &instance); decodeErr != nil {
			t.Errorf("decode %s: %v", path, decodeErr)
			return nil
		}
		if validateErr := schema.Validate(instance); validateErr != nil {
			t.Errorf("%s does not match closed events schema: %v", path, validateErr)
		}
		count++
		return nil
	})
	if err != nil {
		t.Fatalf("walk object events: %v", err)
	}
	if count == 0 {
		t.Fatal("no object events documents were validated")
	}
}

func compileEventsSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	schemaPath := filepath.Join(
		filepath.Dir(thisFile), "..", "..", "..",
		"contracts", "metadata", "_schemas", "events.schema.json",
	)
	schema, err := jsonschema.NewCompiler().Compile(schemaPath)
	if err != nil {
		t.Fatalf("compile events schema: %v", err)
	}
	return schema
}
