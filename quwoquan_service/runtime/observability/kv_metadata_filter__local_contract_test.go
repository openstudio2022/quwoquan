package runtimeobservability

import "testing"

func TestKVMetadataFilter_DefaultMinimal(t *testing.T) {
	filter := NewKVMetadataFilter(nil)
	in, err := filter.FilterInput("Unknown", "op", map[string]any{"a": "1"})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(in) != 0 {
		t.Fatalf("expected empty input kv by default minimal strategy")
	}
}

func TestKVMetadataFilter_Strategies(t *testing.T) {
	filter := NewKVMetadataFilter([]KVPolicy{
		{
			Model:     "Message",
			Operation: "create",
			Input: []KVRule{
				{Key: "content", Strategy: KVStrategyMask},
				{Key: "conversationId", Strategy: KVStrategyAllow},
			},
			Output: []KVRule{
				{Key: "messageId", Strategy: KVStrategyAllow},
				{Key: "raw", Strategy: KVStrategyHash},
			},
		},
	})

	in, err := filter.FilterInput("Message", "create", map[string]any{
		"content":        "hello",
		"conversationId": "c-1",
		"ignored":        "x",
	})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if in["content"] != "***" || in["conversationId"] != "c-1" {
		t.Fatalf("unexpected filtered input: %+v", in)
	}
	if _, ok := in["ignored"]; ok {
		t.Fatalf("unexpected field emitted")
	}

	out, err := filter.FilterOutput("Message", "create", map[string]any{
		"messageId": "m-1",
		"raw":       "raw-value",
	})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if out["messageId"] != "m-1" || out["raw"] != "hash_redacted" {
		t.Fatalf("unexpected filtered output: %+v", out)
	}
}

