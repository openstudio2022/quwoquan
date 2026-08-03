package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportmodel "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/domain/model"
	"quwoquan_service/runtime/controlplane"
)

const (
	reportNamespace  = "config_instance_reports"
	reportObjectType = "config_instance_report"
)

type DocumentStore interface {
	GetDocument(namespace string, id string) (controlplane.Document, bool, error)
	ListDocuments(namespace string) ([]controlplane.Document, error)
}

type StateStore struct {
	documents DocumentStore
	mutations controlplane.AtomicMutationStore
}

func NewStateStore(
	documents DocumentStore,
	mutations controlplane.AtomicMutationStore,
) (*StateStore, error) {
	if documents == nil || mutations == nil {
		return nil, errors.New("config instance report state store requires documents and atomic mutations")
	}
	return &StateStore{documents: documents, mutations: mutations}, nil
}

func (store *StateStore) Commit(
	_ context.Context,
	report reportmodel.Report,
	commandContext reportapp.CommandContext,
) (reportmodel.Report, error) {
	document := reportDocument(report)
	payloadDigest := digestReportCommand(report)
	idempotencyKey := digestParts(
		report.InstanceID,
		report.ReleaseManifestDigest,
		report.EffectiveHash,
		report.ConfigVersion,
	)
	state := "out_of_sync"
	if report.InSync {
		state = "in_sync"
	}
	occurredAt := report.UpdatedAt.UTC().Format(time.RFC3339Nano)
	workflowID := "config-instance-report:" + report.InstanceID
	receipt, err := store.mutations.CommitMutation(controlplane.Mutation{
		Namespace:      reportNamespace,
		ObjectType:     reportObjectType,
		ObjectID:       report.InstanceID,
		Intent:         "report_config_instance",
		PayloadDigest:  payloadDigest,
		IdempotencyKey: idempotencyKey,
		Document:       document,
		Workflow: controlplane.WorkflowState{
			ObjectType: reportObjectType,
			ObjectID:   report.InstanceID,
			WorkflowID: workflowID,
			State:      state,
			History: []controlplane.WorkflowTransition{{
				From: "reported", To: state, Action: "report_config_instance",
				Actor: strings.TrimSpace(commandContext.Actor), At: occurredAt,
			}},
			UpdatedAt: occurredAt,
		},
		Audit: controlplane.AuditEvent{
			AuditID:    "config-instance-report:" + idempotencyKey,
			ObjectType: reportObjectType, ObjectID: report.InstanceID,
			Action: "config_instance_reported", DangerLevel: "medium",
			Actor:       strings.TrimSpace(commandContext.Actor),
			Environment: strings.TrimSpace(commandContext.Environment),
			RequestID:   strings.TrimSpace(commandContext.RequestID),
			TraceID:     strings.TrimSpace(commandContext.TraceID),
			WorkflowRef: workflowID, After: document, At: occurredAt,
		},
		OutboxEvents: []controlplane.MutationOutboxEvent{{
			EventID:   "config-instance-report:" + idempotencyKey,
			EventType: "ConfigInstanceReported", AggregateType: "ConfigInstanceReport",
			AggregateID: report.InstanceID, Payload: document, OccurredAt: occurredAt,
		}},
	})
	if err != nil {
		return reportmodel.Report{}, err
	}
	if !receipt.Replayed {
		return report, nil
	}
	stored, found, err := store.documents.GetDocument(reportNamespace, report.InstanceID)
	if err != nil {
		return reportmodel.Report{}, err
	}
	if !found {
		return reportmodel.Report{}, errors.New("config instance report replay document is missing")
	}
	return decodeReport(stored)
}

func (store *StateStore) List(
	_ context.Context,
) ([]reportmodel.Report, error) {
	documents, err := store.documents.ListDocuments(reportNamespace)
	if err != nil {
		return nil, err
	}
	reports := make([]reportmodel.Report, 0, len(documents))
	for _, document := range documents {
		report, err := decodeReport(document)
		if err != nil {
			return nil, err
		}
		reports = append(reports, report)
	}
	sort.Slice(reports, func(i, j int) bool {
		return reports[i].InstanceID < reports[j].InstanceID
	})
	return reports, nil
}

func reportDocument(report reportmodel.Report) controlplane.Document {
	return controlplane.Document{
		"id": report.InstanceID, "instanceId": report.InstanceID,
		"environment": report.Environment, "cluster": report.Cluster, "service": report.Service,
		"configVersion": report.ConfigVersion, "imageVersion": report.ImageVersion,
		"releaseManifestDigest": report.ReleaseManifestDigest, "desiredHash": report.DesiredHash,
		"effectiveHash": report.EffectiveHash, "inSync": report.InSync, "source": report.Source,
		"updatedAt": report.UpdatedAt.UTC().Format(time.RFC3339Nano), "lastError": report.LastError,
	}
}

func digestReportCommand(report reportmodel.Report) string {
	return digestParts(
		report.InstanceID,
		report.Environment,
		report.Cluster,
		report.Service,
		report.ConfigVersion,
		report.ImageVersion,
		report.ReleaseManifestDigest,
		report.DesiredHash,
		report.EffectiveHash,
		report.Source,
		report.LastError,
	)
}

func digestParts(parts ...string) string {
	digest := sha256.New()
	for _, part := range parts {
		_, _ = digest.Write([]byte(strings.TrimSpace(part)))
		_, _ = digest.Write([]byte{0})
	}
	return hex.EncodeToString(digest.Sum(nil))
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

func decodeReport(document controlplane.Document) (reportmodel.Report, error) {
	updatedAt, err := time.Parse(time.RFC3339Nano, stringValue(document["updatedAt"]))
	if err != nil {
		return reportmodel.Report{}, fmt.Errorf(
			"decode config instance report updatedAt: %w",
			err,
		)
	}
	return reportmodel.Report{
		InstanceID:            stringValue(document["instanceId"]),
		Environment:           stringValue(document["environment"]),
		Cluster:               stringValue(document["cluster"]),
		Service:               stringValue(document["service"]),
		ConfigVersion:         stringValue(document["configVersion"]),
		ImageVersion:          stringValue(document["imageVersion"]),
		ReleaseManifestDigest: stringValue(document["releaseManifestDigest"]),
		DesiredHash:           stringValue(document["desiredHash"]),
		EffectiveHash:         stringValue(document["effectiveHash"]),
		InSync:                boolValue(document["inSync"]),
		Source:                stringValue(document["source"]),
		UpdatedAt:             updatedAt,
		LastError:             stringValue(document["lastError"]),
	}, nil
}
