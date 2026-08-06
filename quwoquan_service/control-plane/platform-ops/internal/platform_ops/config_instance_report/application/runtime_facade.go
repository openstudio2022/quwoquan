package application

import (
	"context"
	"errors"
	"regexp"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
)

const activeAlertsNamespace = "active_alerts"

var (
	ErrAlertNotFound       = errors.New("active alert not found")
	ErrInvalidAlertPayload = errors.New("invalid alertmanager payload")
	canonicalSHA256        = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

type RuntimeStateStore interface {
	GetDocument(namespace, id string) (controlplane.Document, bool, error)
	PutDocument(namespace, id string, doc controlplane.Document) error
	ListDocuments(namespace string) ([]controlplane.Document, error)
	AppendAudit(event controlplane.AuditEvent) error
	ListAudits() ([]controlplane.AuditEvent, error)
	ListAllApprovals() ([]controlplane.ApprovalDecision, error)
}

type RuntimeTopology struct {
	Environments map[string]RuntimeTopologyEnvironment
	Targets      map[string]RuntimeTopologyTarget
}

type RuntimeTopologyEnvironment struct {
	Workloads []RuntimeTopologyWorkload
}

type RuntimeTopologyWorkload struct {
	ID            string
	Plane         string
	DeploymentRef string
}

type RuntimeTopologyTarget struct {
	Environment string
}

type RuntimeTopologyReader interface {
	ReadRuntimeTopology(context.Context) (RuntimeTopology, error)
}

type RuntimeTopologyReaderFunc func(context.Context) (RuntimeTopology, error)

func (reader RuntimeTopologyReaderFunc) ReadRuntimeTopology(
	ctx context.Context,
) (RuntimeTopology, error) {
	return reader(ctx)
}

type AlertmanagerWebhook struct {
	Version  string              `json:"version"`
	GroupKey string              `json:"groupKey"`
	Status   string              `json:"status"`
	Alerts   []AlertmanagerAlert `json:"alerts"`
}

type AlertmanagerAlert struct {
	Status      string            `json:"status"`
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`
	StartsAt    string            `json:"startsAt"`
	EndsAt      string            `json:"endsAt"`
	Fingerprint string            `json:"fingerprint"`
}

type AuditContext struct {
	Actor       string
	Environment string
	RequestID   string
	TraceID     string
}

type RuntimeFacade struct {
	store                 RuntimeStateStore
	topology              RuntimeTopologyReader
	releaseManifestDigest string
	now                   func() time.Time
}

func NewRuntimeFacade(
	store RuntimeStateStore,
	topology RuntimeTopologyReader,
	releaseManifestDigest string,
	now func() time.Time,
) (*RuntimeFacade, error) {
	if store == nil || topology == nil {
		return nil, errors.New("config instance runtime facade requires state store and topology reader")
	}
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &RuntimeFacade{
		store: store, topology: topology,
		releaseManifestDigest: strings.TrimSpace(releaseManifestDigest),
		now:                   now,
	}, nil
}

func (facade *RuntimeFacade) ListReleaseCandidateAcks(
	context.Context,
) ([]map[string]any, error) {
	reports, err := facade.store.ListDocuments("config_instance_reports")
	if err != nil {
		return nil, err
	}
	if !canonicalSHA256.MatchString(facade.releaseManifestDigest) {
		return []map[string]any{}, nil
	}
	type serviceCandidate struct {
		configVersion string
		updatedAt     string
		inSync        bool
	}
	services := map[string]serviceCandidate{}
	for _, report := range reports {
		if stringValue(report["releaseManifestDigest"]) != facade.releaseManifestDigest {
			continue
		}
		service := stringValue(report["service"])
		if service == "" {
			continue
		}
		candidate, found := services[service]
		if found {
			candidate.inSync = candidate.inSync && boolValue(report["inSync"])
		} else {
			candidate.inSync = boolValue(report["inSync"])
		}
		if candidate.configVersion == "" {
			candidate.configVersion = stringValue(report["configVersion"])
		}
		if updatedAt := stringValue(report["updatedAt"]); updatedAt > candidate.updatedAt {
			candidate.updatedAt = updatedAt
		}
		services[service] = candidate
	}
	names := make([]string, 0, len(services))
	for service := range services {
		names = append(names, service)
	}
	sort.Strings(names)
	items := make([]map[string]any, 0, len(names))
	for _, service := range names {
		candidate := services[service]
		state := "drift"
		if candidate.inSync {
			state = "in_sync"
		}
		items = append(items, map[string]any{
			"releaseId": facade.releaseManifestDigest, "service": service,
			"configVersion": candidate.configVersion, "releaseState": state,
			"updatedAt": candidate.updatedAt,
		})
	}
	return items, nil
}

func (facade *RuntimeFacade) ListRuntimeServices(
	ctx context.Context,
) ([]map[string]any, error) {
	topology, err := facade.topology.ReadRuntimeTopology(ctx)
	if err != nil {
		return nil, err
	}
	reports, err := facade.store.ListDocuments("config_instance_reports")
	if err != nil {
		return nil, err
	}
	counts := map[string]int{}
	for _, report := range reports {
		counts[stringValue(report["environment"])+"|"+stringValue(report["service"])]++
	}
	items := make([]map[string]any, 0)
	for environment, environmentTopology := range topology.Environments {
		target := deploymentTarget(topology, environment)
		for _, workload := range environmentTopology.Workloads {
			instances := counts[environment+"|"+workload.ID]
			status := "declared"
			if instances > 0 {
				status = "reporting"
			}
			items = append(items, map[string]any{
				"id": environment + ":" + workload.ID, "environment": environment,
				"cluster": target, "service": workload.ID, "plane": workload.Plane,
				"deploymentRef": workload.DeploymentRef, "instances": instances, "status": status,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["id"].(string) < items[j]["id"].(string) })
	return items, nil
}

func (facade *RuntimeFacade) ListRuntimeInstances(
	context.Context,
) ([]map[string]any, error) {
	reports, err := facade.store.ListDocuments("config_instance_reports")
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, len(reports))
	for _, report := range reports {
		status := "drift"
		if boolValue(report["inSync"]) {
			status = "in-sync"
		}
		items = append(items, map[string]any{
			"id": stringValue(report["instanceId"]), "environment": stringValue(report["environment"]),
			"cluster": stringValue(report["cluster"]), "service": stringValue(report["service"]),
			"plane": "service-plane", "status": status,
		})
	}
	sort.Slice(items, func(i, j int) bool { return items[i]["id"].(string) < items[j]["id"].(string) })
	return items, nil
}

func (facade *RuntimeFacade) IngestAlertmanagerWebhook(
	_ context.Context,
	payload AlertmanagerWebhook,
) (int, error) {
	if len(payload.Alerts) == 0 {
		return 0, ErrInvalidAlertPayload
	}
	ingested := 0
	for _, alert := range payload.Alerts {
		fingerprint := strings.TrimSpace(alert.Fingerprint)
		if fingerprint == "" {
			continue
		}
		current, exists, err := facade.store.GetDocument(activeAlertsNamespace, fingerprint)
		if err != nil {
			return 0, err
		}
		status := strings.TrimSpace(alert.Status)
		if status == "" {
			status = strings.TrimSpace(payload.Status)
		}
		document := controlplane.Document{
			"id": fingerprint, "fingerprint": fingerprint,
			"alertName": alert.Labels["alertname"], "severity": alert.Labels["severity"],
			"service": alert.Labels["service"], "labels": alert.Labels,
			"annotations": alert.Annotations, "startsAt": alert.StartsAt, "endsAt": alert.EndsAt,
			"groupKey": payload.GroupKey, "status": status, "updatedAt": facade.timestamp(),
		}
		if exists && stringValue(current["ackedBy"]) != "" && status == "firing" {
			document["status"] = "acknowledged"
			document["ackedBy"] = current["ackedBy"]
			document["ackedAt"] = current["ackedAt"]
		}
		if err := facade.store.PutDocument(activeAlertsNamespace, fingerprint, document); err != nil {
			return 0, err
		}
		ingested++
	}
	if ingested == 0 {
		return 0, ErrInvalidAlertPayload
	}
	return ingested, nil
}

func (facade *RuntimeFacade) ListActiveAlerts(
	_ context.Context,
	status string,
) ([]controlplane.Document, error) {
	items, err := facade.store.ListDocuments(activeAlertsNamespace)
	if err != nil {
		return nil, err
	}
	status = strings.TrimSpace(status)
	filtered := make([]controlplane.Document, 0, len(items))
	for _, item := range items {
		if status != "" && stringValue(item["status"]) != status {
			continue
		}
		filtered = append(filtered, item)
	}
	sort.Slice(filtered, func(i, j int) bool {
		return stringValue(filtered[i]["updatedAt"]) > stringValue(filtered[j]["updatedAt"])
	})
	return filtered, nil
}

func (facade *RuntimeFacade) AcknowledgeAlert(
	_ context.Context,
	fingerprint string,
	audit AuditContext,
) (controlplane.Document, error) {
	fingerprint = strings.TrimSpace(fingerprint)
	current, found, err := facade.store.GetDocument(activeAlertsNamespace, fingerprint)
	if err != nil {
		return nil, err
	}
	if !found {
		return nil, ErrAlertNotFound
	}
	before := cloneDocument(current)
	current["status"] = "acknowledged"
	current["ackedBy"] = strings.TrimSpace(audit.Actor)
	current["ackedAt"] = facade.timestamp()
	current["updatedAt"] = facade.timestamp()
	if err := facade.store.PutDocument(activeAlertsNamespace, fingerprint, current); err != nil {
		return nil, err
	}
	if err := facade.store.AppendAudit(controlplane.AuditEvent{
		AuditID: "alert_acknowledged", ObjectType: "active_alert", ObjectID: fingerprint,
		Action: "alert_acknowledged", DangerLevel: "high", Actor: strings.TrimSpace(audit.Actor),
		Environment: strings.TrimSpace(audit.Environment), RequestID: strings.TrimSpace(audit.RequestID),
		TraceID: strings.TrimSpace(audit.TraceID), Before: before, After: cloneDocument(current),
	}); err != nil {
		return nil, err
	}
	return current, nil
}

func (facade *RuntimeFacade) ListPlatformAudits(
	context.Context,
) ([]controlplane.AuditEvent, error) {
	return facade.store.ListAudits()
}

func (facade *RuntimeFacade) ListPlatformApprovals(
	context.Context,
) ([]controlplane.ApprovalDecision, error) {
	return facade.store.ListAllApprovals()
}

func (facade *RuntimeFacade) timestamp() string {
	return facade.now().UTC().Format(time.RFC3339)
}

func deploymentTarget(topology RuntimeTopology, environment string) string {
	preferred := environment + "-local"
	if environment == "prod" {
		preferred = "prod-hosted"
	}
	if target, ok := topology.Targets[preferred]; ok && target.Environment == environment {
		return preferred
	}
	for targetID, target := range topology.Targets {
		if target.Environment == environment {
			return targetID
		}
	}
	return environment
}

func stringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func boolValue(value any) bool {
	flag, _ := value.(bool)
	return flag
}

func cloneDocument(in controlplane.Document) controlplane.Document {
	if in == nil {
		return nil
	}
	out := make(controlplane.Document, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}
