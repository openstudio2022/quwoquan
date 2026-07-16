package config_layer

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	"quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
)

type Facade struct {
	store   ports.AggregateStore
	reader  ports.LayerReader
	catalog ports.ConfigKeyCatalog
	now     func() time.Time
}

type SetValueCommand struct {
	LayerID         string            `json:"layerId"`
	ExpectedVersion int64             `json:"expectedVersion"`
	Scope           model.Scope       `json:"scope"`
	ConfigKey       string            `json:"configKey"`
	Value           model.ConfigValue `json:"value"`
	IdempotencyKey  string            `json:"-"`
}

type EffectiveConfigItem struct {
	Key           string            `json:"key"`
	Value         model.ConfigValue `json:"value"`
	SourceLayerID string            `json:"sourceLayerId"`
}

type EffectiveConfigSlice struct {
	Items         []EffectiveConfigItem `json:"items"`
	EffectiveHash string                `json:"effectiveHash"`
}

func NewFacade(
	store ports.AggregateStore,
	reader ports.LayerReader,
	catalog ports.ConfigKeyCatalog,
) (*Facade, error) {
	if store == nil || reader == nil || catalog == nil {
		return nil, fmt.Errorf("config layer store, reader and generated key catalog are required")
	}
	return &Facade{store: store, reader: reader, catalog: catalog, now: time.Now}, nil
}

func (f *Facade) ListConfigKeys(context.Context) []ports.ConfigKeyDescriptor {
	return f.catalog.List()
}

func (f *Facade) ListLayers(ctx context.Context) ([]model.ConfigLayer, error) {
	return f.reader.List(ctx)
}

func (f *Facade) SetValue(ctx context.Context, command SetValueCommand) (ports.CommitReceipt, model.ConfigLayer, error) {
	command.LayerID = strings.TrimSpace(command.LayerID)
	command.ConfigKey = strings.TrimSpace(command.ConfigKey)
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	command.Scope = command.Scope.Normalized()
	if command.LayerID == "" || command.ConfigKey == "" || command.IdempotencyKey == "" {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand("layerId, configKey and Idempotency-Key are required")
	}
	if command.ExpectedVersion < 0 {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand("expectedVersion cannot be negative")
	}
	if err := command.Scope.Validate(); err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand(err.Error())
	}
	if command.LayerID != command.Scope.LayerID() {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand("layerId must equal canonical scope id")
	}
	descriptor, found := f.catalog.Get(command.ConfigKey)
	if !found {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand(fmt.Sprintf("config key %q is not registered", command.ConfigKey))
	}
	payload, err := json.Marshal(command)
	if err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand(err.Error())
	}
	commandDigest := fmt.Sprintf("%x", sha256.Sum256(payload))
	if receipt, found, err := f.store.Replay(ctx, command.LayerID, command.IdempotencyKey, commandDigest); err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, err
	} else if found {
		layer, loadErr := f.store.Load(ctx, command.LayerID)
		return receipt, layer, loadErr
	}

	var current model.ConfigLayer
	if command.ExpectedVersion == 0 {
		current, err = model.NewConfigLayer(command.Scope, f.now())
	} else {
		current, err = f.store.Load(ctx, command.LayerID)
	}
	if err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, err
	}
	now := f.now().UTC()
	next, err := current.SetValue(command.ConfigKey, command.Value, descriptor.Kind, descriptor.Scope, now)
	if err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, invalidCommand(err.Error())
	}
	eventPayload, err := json.Marshal(next)
	if err != nil {
		return ports.CommitReceipt{}, model.ConfigLayer{}, err
	}
	eventDigest := sha256.Sum256([]byte(command.LayerID + "\x00" + command.IdempotencyKey))
	receipt, err := f.store.Commit(ctx, command.ExpectedVersion, ports.ChangeSet{
		Layer: next, IdempotencyKey: command.IdempotencyKey, CommandDigest: commandDigest,
		Events: []model.Event{{
			ID:   "config-layer-value-set-" + fmt.Sprintf("%x", eventDigest[:16]),
			Type: "ConfigLayerValueSet", AggregateID: next.ID, AggregateType: "ConfigLayer",
			Payload: eventPayload, OccurredAt: now,
		}},
	})
	return receipt, next, err
}

func invalidCommand(message string) error {
	return fmt.Errorf("%w: %s", model.ErrInvalid, message)
}

func (f *Facade) Resolve(ctx context.Context, scope model.Scope) (EffectiveConfigSlice, error) {
	if strings.TrimSpace(scope.Environment) == "" {
		return EffectiveConfigSlice{}, fmt.Errorf("resolve requires environment")
	}
	layers, err := f.reader.List(ctx)
	if err != nil {
		return EffectiveConfigSlice{}, err
	}
	resolved := make(map[string]EffectiveConfigItem, len(f.catalog.List()))
	for _, descriptor := range f.catalog.List() {
		resolved[descriptor.Key] = EffectiveConfigItem{
			Key: descriptor.Key, Value: descriptor.Default, SourceLayerID: "metadata-default",
		}
	}
	sort.Slice(layers, func(i, j int) bool {
		left, right := scopeRank(layers[i].Scope.Level), scopeRank(layers[j].Scope.Level)
		if left == right {
			return layers[i].ID < layers[j].ID
		}
		return left < right
	})
	for _, layer := range layers {
		if !scopeMatches(layer.Scope, scope) || layer.Status != "active" {
			continue
		}
		for _, entry := range layer.Entries {
			resolved[entry.Key] = EffectiveConfigItem{Key: entry.Key, Value: entry.Value, SourceLayerID: layer.ID}
		}
	}
	items := make([]EffectiveConfigItem, 0, len(resolved))
	for _, item := range resolved {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].Key < items[j].Key })
	raw, err := json.Marshal(items)
	if err != nil {
		return EffectiveConfigSlice{}, err
	}
	hash := sha256.Sum256(raw)
	return EffectiveConfigSlice{Items: items, EffectiveHash: fmt.Sprintf("%x", hash[:])}, nil
}

func scopeRank(level string) int {
	switch level {
	case "global":
		return 0
	case "environment":
		return 1
	case "cluster":
		return 2
	case "service":
		return 3
	default:
		return 4
	}
}

func scopeMatches(layer, target model.Scope) bool {
	switch layer.Level {
	case "global":
		return true
	case "environment":
		return layer.Environment == target.Environment
	case "cluster":
		return layer.Environment == target.Environment && layer.Cluster == target.Cluster
	case "service":
		return layer.Environment == target.Environment && layer.Cluster == target.Cluster && layer.Service == target.Service
	default:
		return false
	}
}
