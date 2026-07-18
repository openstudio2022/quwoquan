package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	confighttp "quwoquan_service/services/platform-ops-service/internal/adapters/http/config_layer"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
	configmodel "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/model"
	configports "quwoquan_service/services/platform-ops-service/internal/domain/platform_ops/config_layer/ports"
)

func TestConfigLayerHTTPBoundaryIsTypedIdempotentAndStrict(t *testing.T) {
	store := newLocalConfigLayerStore()
	catalog := localConfigCatalog()
	facade, err := configapp.NewFacade(store, store, catalog)
	if err != nil {
		t.Fatalf("build config facade: %v", err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("build config handler: %v", err)
	}
	path := "/control-plane/platform/configs/sys.content.mongo.max_pool_size:update"
	body := []byte(`{"layerId":"service:gamma:gamma-user-a:content-service","scopeLevel":"service","scopeId":"content-service","environment":"gamma","cluster":"gamma-user-a","service":"content-service","value":{"kind":"int","intValue":120}}`)

	first := performLocalConfigRequest(handler, path, body, "config-idem-1")
	if first.Code != http.StatusOK {
		t.Fatalf("first config write status=%d body=%s", first.Code, first.Body.String())
	}
	replay := performLocalConfigRequest(handler, path, body, "config-idem-1")
	if replay.Code != http.StatusOK {
		t.Fatalf("config replay status=%d body=%s", replay.Code, replay.Body.String())
	}
	if got := store.eventCount(); got != 1 {
		t.Fatalf("idempotent replay emitted %d events, want 1", got)
	}

	wrongKind := []byte(`{"layerId":"service:content-service","scopeLevel":"service","scopeId":"content-service","environment":"gamma","cluster":"gamma-user-a","service":"content-service","value":{"kind":"string","stringValue":"120"}}`)
	wrong := performLocalConfigRequest(handler, path, wrongKind, "config-idem-2")
	if wrong.Code != http.StatusBadRequest {
		t.Fatalf("wrong value kind status=%d body=%s", wrong.Code, wrong.Body.String())
	}

	unknownField := append(body[:len(body)-1], []byte(`,"unexpectedValue":120}`)...)
	unknown := performLocalConfigRequest(handler, path, unknownField, "config-idem-3")
	if unknown.Code != http.StatusBadRequest {
		t.Fatalf("unknown request field status=%d body=%s", unknown.Code, unknown.Body.String())
	}

	resolved := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/resolve?env=gamma&cluster=gamma-user-a&service=content-service", nil)
	handler.ServeHTTP(resolved, request)
	if resolved.Code != http.StatusOK {
		t.Fatalf("resolve status=%d body=%s", resolved.Code, resolved.Body.String())
	}
	var result configapp.EffectiveConfigSlice
	if err := json.Unmarshal(resolved.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode resolve response: %v", err)
	}
	if len(result.Items) != 1 || result.Items[0].SourceLayerID != "service:gamma:gamma-user-a:content-service" {
		t.Fatalf("resolved config did not use service layer: %+v", result)
	}
}

func performLocalConfigRequest(handler http.Handler, path string, body []byte, idempotencyKey string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.Header.Set("If-Match", `"0"`)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

type localConfigLayerStore struct {
	mu       sync.Mutex
	layers   map[string]configmodel.ConfigLayer
	receipts map[string]localReceipt
	events   []configmodel.Event
}

type localReceipt struct {
	digest  string
	receipt configports.CommitReceipt
}

func newLocalConfigLayerStore() *localConfigLayerStore {
	return &localConfigLayerStore{
		layers: map[string]configmodel.ConfigLayer{}, receipts: map[string]localReceipt{},
	}
}

func (s *localConfigLayerStore) Load(_ context.Context, id string) (configmodel.ConfigLayer, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	layer, found := s.layers[id]
	if !found {
		return configmodel.ConfigLayer{}, configmodel.ErrNotFound
	}
	return layer, nil
}

func (s *localConfigLayerStore) List(context.Context) ([]configmodel.ConfigLayer, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]configmodel.ConfigLayer, 0, len(s.layers))
	for _, layer := range s.layers {
		items = append(items, layer)
	}
	return items, nil
}

func (s *localConfigLayerStore) Replay(
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

func (s *localConfigLayerStore) Commit(
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
	s.events = append(s.events, changes.Events...)
	receipt := configports.CommitReceipt{LayerID: changes.Layer.ID, Version: changes.Layer.Version}
	s.receipts[key] = localReceipt{digest: changes.CommandDigest, receipt: receipt}
	return receipt, nil
}

func (s *localConfigLayerStore) eventCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.events)
}

type localCatalog struct {
	item configports.ConfigKeyDescriptor
}

func localConfigCatalog() *localCatalog {
	defaultValue := int64(100)
	return &localCatalog{item: configports.ConfigKeyDescriptor{
		Key: "sys.content.mongo.max_pool_size", Kind: configmodel.ValueKindInt,
		Scope: "service", Default: configmodel.ConfigValue{Kind: configmodel.ValueKindInt, IntValue: &defaultValue},
	}}
}

func (c *localCatalog) Get(key string) (configports.ConfigKeyDescriptor, bool) {
	return c.item, key == c.item.Key
}

func (c *localCatalog) List() []configports.ConfigKeyDescriptor {
	return []configports.ConfigKeyDescriptor{c.item}
}

var (
	_ configports.AggregateStore   = (*localConfigLayerStore)(nil)
	_ configports.LayerReader      = (*localConfigLayerStore)(nil)
	_ configports.ConfigKeyCatalog = (*localCatalog)(nil)
)
