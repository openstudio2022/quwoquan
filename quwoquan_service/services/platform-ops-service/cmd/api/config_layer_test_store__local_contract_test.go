package main

import (
	"context"
	"sync"
	"testing"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	confighttp "quwoquan_service/services/platform-ops-service/internal/adapters/http/config_layer"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
	configmodel "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	configports "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
	configpersistence "quwoquan_service/services/platform-ops-service/internal/infrastructure/platform_ops/config_layer/persistence"
)

type testConfigLayerStore struct {
	mu       sync.Mutex
	layers   map[string]configmodel.ConfigLayer
	receipts map[string]testConfigReceipt
}

type testConfigReceipt struct {
	digest  string
	receipt configports.CommitReceipt
}

func newTestConfigLayerComponents(t *testing.T) (*configapp.Facade, *confighttp.Handler) {
	t.Helper()
	store := &testConfigLayerStore{
		layers: map[string]configmodel.ConfigLayer{}, receipts: map[string]testConfigReceipt{},
	}
	catalog, err := configpersistence.NewGeneratedConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfigSchema(),
	)
	if err != nil {
		t.Fatalf("build generated config catalog: %v", err)
	}
	facade, err := configapp.NewFacade(store, store, catalog)
	if err != nil {
		t.Fatalf("build config facade: %v", err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("build config handler: %v", err)
	}
	return facade, handler
}

func (s *testConfigLayerStore) Load(_ context.Context, id string) (configmodel.ConfigLayer, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	layer, found := s.layers[id]
	if !found {
		return configmodel.ConfigLayer{}, configmodel.ErrNotFound
	}
	return layer, nil
}

func (s *testConfigLayerStore) List(context.Context) ([]configmodel.ConfigLayer, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]configmodel.ConfigLayer, 0, len(s.layers))
	for _, layer := range s.layers {
		items = append(items, layer)
	}
	return items, nil
}

func (s *testConfigLayerStore) Replay(
	_ context.Context,
	layerID, idempotencyKey, digest string,
) (configports.CommitReceipt, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	stored, found := s.receipts[layerID+"\x00"+idempotencyKey]
	if !found {
		return configports.CommitReceipt{}, false, nil
	}
	if stored.digest != digest {
		return configports.CommitReceipt{}, false, configmodel.ErrIdempotencyConflict
	}
	receipt := stored.receipt
	receipt.Replayed = true
	return receipt, true, nil
}

func (s *testConfigLayerStore) Commit(
	_ context.Context,
	expectedVersion int64,
	changes configports.ChangeSet,
) (configports.CommitReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := changes.Layer.ID + "\x00" + changes.IdempotencyKey
	if stored, found := s.receipts[key]; found {
		if stored.digest != changes.CommandDigest {
			return configports.CommitReceipt{}, configmodel.ErrIdempotencyConflict
		}
		receipt := stored.receipt
		receipt.Replayed = true
		return receipt, nil
	}
	current, found := s.layers[changes.Layer.ID]
	if (!found && expectedVersion != 0) || (found && current.Version != expectedVersion) {
		return configports.CommitReceipt{}, configmodel.ErrVersionConflict
	}
	s.layers[changes.Layer.ID] = changes.Layer
	receipt := configports.CommitReceipt{LayerID: changes.Layer.ID, Version: changes.Layer.Version}
	s.receipts[key] = testConfigReceipt{digest: changes.CommandDigest, receipt: receipt}
	return receipt, nil
}

var (
	_ configports.AggregateStore = (*testConfigLayerStore)(nil)
	_ configports.LayerReader    = (*testConfigLayerStore)(nil)
)

func TestConfigLayerTestComponentsExposeGeneratedCatalogAndEmptyReader(t *testing.T) {
	facade, handler := newTestConfigLayerComponents(t)
	if handler == nil {
		t.Fatal("expected typed config layer HTTP handler")
	}
	if keys := facade.ListConfigKeys(context.Background()); len(keys) == 0 {
		t.Fatal("expected generated config key catalog")
	}
	layers, err := facade.ListLayers(context.Background())
	if err != nil {
		t.Fatalf("list empty config layers: %v", err)
	}
	if len(layers) != 0 {
		t.Fatalf("expected empty aggregate reader, got %d layers", len(layers))
	}
}
