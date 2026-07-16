package ports

import (
	"context"

	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
)

type ChangeSet struct {
	Layer          model.ConfigLayer
	Events         []model.Event
	IdempotencyKey string
	CommandDigest  string
}

type CommitReceipt struct {
	LayerID  string `json:"layerId"`
	Version  int64  `json:"version"`
	Replayed bool   `json:"replayed"`
}

type ConfigKeyDescriptor struct {
	Key        string            `json:"key"`
	Kind       model.ValueKind   `json:"kind"`
	Owner      string            `json:"owner"`
	Scope      string            `json:"scope"`
	Reload     string            `json:"reload"`
	Rollout    string            `json:"rollout"`
	RiskLevel  string            `json:"riskLevel"`
	UIEditable bool              `json:"uiEditable"`
	Default    model.ConfigValue `json:"default"`
}

type AggregateStore interface {
	Load(context.Context, string) (model.ConfigLayer, error)
	Replay(context.Context, string, string, string) (CommitReceipt, bool, error)
	Commit(context.Context, int64, ChangeSet) (CommitReceipt, error)
}

type LayerReader interface {
	List(context.Context) ([]model.ConfigLayer, error)
}

type ConfigKeyCatalog interface {
	Get(string) (ConfigKeyDescriptor, bool)
	List() []ConfigKeyDescriptor
}
