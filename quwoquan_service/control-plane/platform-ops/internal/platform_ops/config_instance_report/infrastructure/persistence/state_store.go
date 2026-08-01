package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	reportmodel "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/domain/model"
)

type DocumentStore interface {
	PutDocument(collection, id string, document map[string]any) error
	ListDocuments(collection string) ([]map[string]any, error)
}

type StateStore struct{ store DocumentStore }

func NewStateStore(store DocumentStore) *StateStore { return &StateStore{store: store} }

func (s *StateStore) Put(_ context.Context, report reportmodel.Report) error {
	if s == nil || s.store == nil {
		return errors.New("config instance report state store is unavailable")
	}
	return s.store.PutDocument("config_instance_reports", report.InstanceID, map[string]any{
		"id": report.InstanceID, "instanceId": report.InstanceID,
		"environment": report.Environment, "cluster": report.Cluster, "service": report.Service,
		"configVersion": report.ConfigVersion, "imageVersion": report.ImageVersion,
		"releaseManifestDigest": report.ReleaseManifestDigest, "desiredHash": report.DesiredHash,
		"effectiveHash": report.EffectiveHash, "inSync": report.InSync, "source": report.Source,
		"updatedAt": report.UpdatedAt.Format(time.RFC3339), "lastError": report.LastError,
	})
}

func (s *StateStore) List(_ context.Context) ([]reportmodel.Report, error) {
	if s == nil || s.store == nil {
		return nil, errors.New("config instance report state store is unavailable")
	}
	documents, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		return nil, err
	}
	reports := make([]reportmodel.Report, 0, len(documents))
	for _, document := range documents {
		updatedAt, err := time.Parse(time.RFC3339, stringValue(document["updatedAt"]))
		if err != nil {
			return nil, fmt.Errorf("decode config instance report updatedAt: %w", err)
		}
		reports = append(reports, reportmodel.Report{
			InstanceID: stringValue(document["instanceId"]), Environment: stringValue(document["environment"]),
			Cluster: stringValue(document["cluster"]), Service: stringValue(document["service"]),
			ConfigVersion: stringValue(document["configVersion"]), ImageVersion: stringValue(document["imageVersion"]),
			ReleaseManifestDigest: stringValue(document["releaseManifestDigest"]), DesiredHash: stringValue(document["desiredHash"]),
			EffectiveHash: stringValue(document["effectiveHash"]), InSync: boolValue(document["inSync"]),
			Source: stringValue(document["source"]), UpdatedAt: updatedAt, LastError: stringValue(document["lastError"]),
		})
	}
	return reports, nil
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}

func boolValue(value any) bool {
	parsed, _ := value.(bool)
	return parsed
}
