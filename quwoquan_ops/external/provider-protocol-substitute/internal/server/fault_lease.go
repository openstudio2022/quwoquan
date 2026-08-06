package server

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	maximumFaultLeaseTTLSeconds = 300
	maximumFaultLeaseMatches    = 1000
	maximumInvocationLedgerSize = 2048
)

var (
	faultLeaseIDPattern = regexp.MustCompile(`^fault-[0-9a-f]{32}$`)
	faultOwnerPattern   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$`)

	allowedFaultScenarios = map[string]struct{}{
		"validation":             {},
		"auth":                   {},
		"delay_timeout":          {},
		"throttle":               {},
		"transient_then_success": {},
		"unavailable":            {},
	}

	canonicalProviderScopes = map[string]map[string]struct{}{
		"assistant.model.generation": {
			"complete": {},
			"stream":   {},
		},
		"assistant.public.search": {
			"search": {},
		},
		"assistant.weather.forecast": {
			"forecast": {},
		},
		"assistant.finance.quote": {
			"quote": {},
		},
		"content.embedding.generation": {
			"embed": {},
		},
		"integration.location.lookup": {
			"nearby": {},
			"search": {},
		},
		"identity.carrier.one_tap": {
			"resolvePhone": {},
		},
		"identity.social.login": {
			"authorize":       {},
			"resolveIdentity": {},
		},
		"integration.push.delivery": {
			"deliver": {},
		},
	}
)

type FaultParameters struct {
	DelayMillis       int `json:"delayMillis,omitempty"`
	RemainingFailures int `json:"remainingFailures,omitempty"`
	RetryAfterSeconds int `json:"retryAfterSeconds,omitempty"`
}

type FaultCleanupReceipt struct {
	Status       string    `json:"status"`
	Reason       string    `json:"reason"`
	ReceiptRef   string    `json:"receiptRef"`
	LeaseVersion uint64    `json:"leaseVersion"`
	RestoredAt   time.Time `json:"restoredAt"`
}

type FaultLease struct {
	LeaseID                  string               `json:"leaseId"`
	Environment              string               `json:"environment"`
	Target                   string               `json:"target"`
	ConfigurationDigest      string               `json:"configurationDigest"`
	RuntimeCompositionDigest string               `json:"runtimeCompositionDigest"`
	CapabilityID             string               `json:"capabilityId"`
	Operation                string               `json:"operation"`
	Scenario                 string               `json:"scenario"`
	Parameters               FaultParameters      `json:"parameters"`
	Owner                    string               `json:"owner"`
	Version                  uint64               `json:"version"`
	ActivatedAt              time.Time            `json:"activatedAt"`
	ExpiresAt                time.Time            `json:"expiresAt"`
	MaxMatches               uint64               `json:"maxMatches"`
	MatchedCount             uint64               `json:"matchedCount"`
	RemainingFailures        int                  `json:"remainingFailures"`
	State                    string               `json:"state"`
	CleanupReceipt           *FaultCleanupReceipt `json:"cleanupReceipt,omitempty"`
}

type ActiveFaultLeaseSummary struct {
	LeaseID           string    `json:"leaseId"`
	CapabilityID      string    `json:"capabilityId"`
	Operation         string    `json:"operation"`
	Scenario          string    `json:"scenario"`
	Version           uint64    `json:"version"`
	ExpiresAt         time.Time `json:"expiresAt"`
	MaxMatches        uint64    `json:"maxMatches"`
	MatchedCount      uint64    `json:"matchedCount"`
	RemainingFailures int       `json:"remainingFailures"`
}

type InvocationLedgerEntry struct {
	LeaseID              string    `json:"leaseId"`
	CapabilityID         string    `json:"capabilityId"`
	Operation            string    `json:"operation"`
	CallOrdinal          uint64    `json:"callOrdinal"`
	EffectOrdinal        uint64    `json:"effectOrdinal"`
	RequestDigest        string    `json:"requestDigest"`
	TraceDigest          string    `json:"traceDigest"`
	Outcome              string    `json:"outcome"`
	Status               int       `json:"status"`
	LatencyMillis        int64     `json:"latencyMillis"`
	ObservedAt           time.Time `json:"observedAt"`
	IdempotencyKeyDigest string    `json:"idempotencyKeyDigest,omitempty"`
	IdempotencyState     string    `json:"idempotencyState"`
	NetworkHostDigest    string    `json:"networkHostDigest"`
	TLSServerNameDigest  string    `json:"tlsServerNameDigest,omitempty"`
	TLSVersion           string    `json:"tlsVersion,omitempty"`
}

type acquireFaultLeaseRequest struct {
	Environment              string           `json:"environment"`
	Target                   string           `json:"target"`
	ConfigurationDigest      string           `json:"configurationDigest"`
	RuntimeCompositionDigest string           `json:"runtimeCompositionDigest"`
	CapabilityID             string           `json:"capabilityId"`
	Operation                string           `json:"operation"`
	Scenario                 string           `json:"scenario"`
	Parameters               *FaultParameters `json:"parameters"`
	Owner                    string           `json:"owner"`
	TTLSeconds               int              `json:"ttlSeconds"`
	MaxMatches               uint64           `json:"maxMatches"`
}

type releaseFaultLeaseRequest struct {
	Owner           string `json:"owner"`
	ExpectedVersion uint64 `json:"expectedVersion"`
}

type faultDecision struct {
	LeaseID          string
	Scenario         string
	Delay            time.Duration
	RetryAfter       int
	ShouldApplyFault bool
}

func (s *Server) acquireFaultLease(writer http.ResponseWriter, request *http.Request) {
	var payload acquireFaultLeaseRequest
	if err := decodeStrictJSON(writer, request, 16<<10, &payload); err != nil {
		return
	}
	if err := s.validateFaultLeaseRequest(payload); err != nil {
		http.Error(writer, "invalid fault lease request", http.StatusBadRequest)
		return
	}
	leaseID, err := newFaultLeaseID()
	if err != nil {
		http.Error(writer, "fault lease unavailable", http.StatusInternalServerError)
		return
	}
	now := s.now().UTC()
	lease := &FaultLease{
		LeaseID:                  leaseID,
		Environment:              s.environment,
		Target:                   s.target,
		ConfigurationDigest:      s.configurationDigest,
		RuntimeCompositionDigest: s.runtimeCompositionDigest,
		CapabilityID:             payload.CapabilityID,
		Operation:                payload.Operation,
		Scenario:                 payload.Scenario,
		Parameters:               *payload.Parameters,
		Owner:                    payload.Owner,
		Version:                  1,
		ActivatedAt:              now,
		ExpiresAt:                now.Add(time.Duration(payload.TTLSeconds) * time.Second),
		MaxMatches:               payload.MaxMatches,
		RemainingFailures:        payload.Parameters.RemainingFailures,
		State:                    "active",
	}
	scope := providerScopeKey(payload.CapabilityID, payload.Operation)

	s.mu.Lock()
	s.expireFaultLeasesLocked(now)
	if _, exists := s.activeLeaseByScope[scope]; exists {
		s.mu.Unlock()
		http.Error(writer, "fault lease scope is already active", http.StatusConflict)
		return
	}
	if _, exists := s.leases[leaseID]; exists {
		s.mu.Unlock()
		http.Error(writer, "fault lease identity collision", http.StatusInternalServerError)
		return
	}
	s.leases[leaseID] = lease
	s.activeLeaseByScope[scope] = leaseID
	response := *lease
	s.mu.Unlock()

	writeJSON(writer, http.StatusCreated, response)
}

func (s *Server) readFaultLease(writer http.ResponseWriter, request *http.Request) {
	leaseID := strings.TrimSpace(request.PathValue("leaseId"))
	if !faultLeaseIDPattern.MatchString(leaseID) {
		http.Error(writer, "invalid fault lease identity", http.StatusBadRequest)
		return
	}
	s.mu.Lock()
	s.expireFaultLeasesLocked(s.now().UTC())
	lease, found := s.leases[leaseID]
	if !found {
		s.mu.Unlock()
		http.Error(writer, "fault lease not found", http.StatusNotFound)
		return
	}
	response := *lease
	s.mu.Unlock()
	writeJSON(writer, http.StatusOK, response)
}

func (s *Server) releaseFaultLease(writer http.ResponseWriter, request *http.Request) {
	leaseID := strings.TrimSpace(request.PathValue("leaseId"))
	if !faultLeaseIDPattern.MatchString(leaseID) {
		http.Error(writer, "invalid fault lease identity", http.StatusBadRequest)
		return
	}
	var payload releaseFaultLeaseRequest
	if err := decodeStrictJSON(writer, request, 4096, &payload); err != nil {
		return
	}
	if !faultOwnerPattern.MatchString(payload.Owner) || payload.ExpectedVersion == 0 {
		http.Error(writer, "invalid fault lease release", http.StatusBadRequest)
		return
	}

	s.mu.Lock()
	s.expireFaultLeasesLocked(s.now().UTC())
	lease, found := s.leases[leaseID]
	if !found {
		s.mu.Unlock()
		http.Error(writer, "fault lease not found", http.StatusNotFound)
		return
	}
	if lease.State != "active" ||
		lease.Owner != payload.Owner ||
		lease.Version != payload.ExpectedVersion {
		s.mu.Unlock()
		http.Error(writer, "fault lease release conflict", http.StatusConflict)
		return
	}
	s.finalizeFaultLeaseLocked(lease, "released", s.now().UTC())
	response := *lease
	s.mu.Unlock()
	writeJSON(writer, http.StatusOK, response)
}

func (s *Server) readback(writer http.ResponseWriter, _ *http.Request) {
	now := s.now().UTC()
	s.mu.Lock()
	s.expireFaultLeasesLocked(now)
	counts := make(map[string]uint64, len(s.counts))
	for scope, count := range s.counts {
		counts[scope] = count
	}
	effectCounts := make(map[string]uint64, len(s.effectCounts))
	for scope, count := range s.effectCounts {
		effectCounts[scope] = count
	}
	ledger := append([]InvocationLedgerEntry(nil), s.ledger...)
	leases := make([]FaultLease, 0, len(s.leases))
	for _, lease := range s.leases {
		leases = append(leases, *lease)
	}
	s.expireCallbackChannelsLocked(now)
	callbackChannels := sortedCallbackChannels(s.callbackChannels)
	s.mu.Unlock()
	sort.Slice(leases, func(left, right int) bool {
		return leases[left].LeaseID < leases[right].LeaseID
	})
	writeJSON(writer, http.StatusOK, map[string]any{
		"adapterId":                AdapterID,
		"environment":              s.environment,
		"target":                   s.target,
		"configurationDigest":      s.configurationDigest,
		"runtimeCompositionDigest": s.runtimeCompositionDigest,
		"nonPromotable":            true,
		"calls":                    counts,
		"effects":                  effectCounts,
		"faultLeases":              leases,
		"callbackChannels":         callbackChannels,
		"invocations":              ledger,
	})
}

func (s *Server) activeLeaseSummaries() []ActiveFaultLeaseSummary {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireFaultLeasesLocked(s.now().UTC())
	summaries := make([]ActiveFaultLeaseSummary, 0, len(s.activeLeaseByScope))
	for _, leaseID := range s.activeLeaseByScope {
		lease := s.leases[leaseID]
		if lease == nil || lease.State != "active" {
			continue
		}
		summaries = append(summaries, ActiveFaultLeaseSummary{
			LeaseID:           lease.LeaseID,
			CapabilityID:      lease.CapabilityID,
			Operation:         lease.Operation,
			Scenario:          lease.Scenario,
			Version:           lease.Version,
			ExpiresAt:         lease.ExpiresAt,
			MaxMatches:        lease.MaxMatches,
			MatchedCount:      lease.MatchedCount,
			RemainingFailures: lease.RemainingFailures,
		})
	}
	sort.Slice(summaries, func(left, right int) bool {
		if summaries[left].CapabilityID == summaries[right].CapabilityID {
			return summaries[left].Operation < summaries[right].Operation
		}
		return summaries[left].CapabilityID < summaries[right].CapabilityID
	})
	return summaries
}

func (s *Server) validateFaultLeaseRequest(payload acquireFaultLeaseRequest) error {
	if payload.Environment != s.environment ||
		payload.Target != s.target ||
		payload.ConfigurationDigest != s.configurationDigest ||
		payload.RuntimeCompositionDigest != s.runtimeCompositionDigest {
		return errors.New("fault lease runtime identity mismatch")
	}
	operations, found := canonicalProviderScopes[payload.CapabilityID]
	if !found {
		return errors.New("fault lease capability is not canonical")
	}
	if _, found := operations[payload.Operation]; !found {
		return errors.New("fault lease operation is not canonical")
	}
	if _, found := allowedFaultScenarios[payload.Scenario]; !found {
		return errors.New("fault lease scenario is unsupported")
	}
	if !faultOwnerPattern.MatchString(payload.Owner) {
		return errors.New("fault lease owner is invalid")
	}
	if payload.TTLSeconds < 1 || payload.TTLSeconds > maximumFaultLeaseTTLSeconds {
		return errors.New("fault lease TTL is invalid")
	}
	if payload.MaxMatches < 1 || payload.MaxMatches > maximumFaultLeaseMatches {
		return errors.New("fault lease match bound is invalid")
	}
	if payload.Parameters == nil {
		return errors.New("fault lease parameters are required")
	}
	parameters := *payload.Parameters
	switch payload.Scenario {
	case "validation", "auth", "unavailable":
		if parameters != (FaultParameters{}) {
			return errors.New("fault lease scenario forbids parameters")
		}
	case "delay_timeout":
		if parameters.DelayMillis < 1 || parameters.DelayMillis > 30_000 ||
			parameters.RemainingFailures != 0 || parameters.RetryAfterSeconds != 0 {
			return errors.New("fault lease delay parameters are invalid")
		}
	case "throttle":
		if parameters.RetryAfterSeconds < 1 || parameters.RetryAfterSeconds > 60 ||
			parameters.DelayMillis != 0 || parameters.RemainingFailures != 0 {
			return errors.New("fault lease throttle parameters are invalid")
		}
	case "transient_then_success":
		if parameters.RemainingFailures < 1 ||
			uint64(parameters.RemainingFailures) >= payload.MaxMatches ||
			parameters.DelayMillis != 0 || parameters.RetryAfterSeconds != 0 {
			return errors.New("fault lease transient parameters are invalid")
		}
	}
	return nil
}

func (s *Server) invokeProvider(
	writer http.ResponseWriter,
	request *http.Request,
	capabilityID string,
	operation string,
	next http.HandlerFunc,
) {
	startedAt := s.now().UTC()
	callOrdinal := s.nextCallOrdinal()
	evidence := requestEvidence(request)
	tracked := &responseCapture{ResponseWriter: writer}
	outcome := "success"
	leaseID := ""
	effectApplied := true
	effectOrdinal := callOrdinal
	idempotency := s.beginIdempotency(
		providerScopeKey(capabilityID, operation),
		evidence,
		callOrdinal,
	)
	if !s.validateCallbackChannel(
		evidence.CallbackChannelID,
		capabilityID,
		operation,
	) {
		http.Error(tracked, "callback channel conflict", http.StatusConflict)
		outcome = "callback_channel_rejected"
		effectApplied = false
	} else if idempotency.State == "conflict" {
		http.Error(tracked, "idempotency conflict", http.StatusConflict)
		outcome = "idempotency_conflict"
		effectApplied = false
		effectOrdinal = idempotency.Record.EffectOrdinal
	} else if idempotency.State == "capacity" {
		http.Error(tracked, "idempotency capacity unavailable", http.StatusServiceUnavailable)
		outcome = "idempotency_capacity_unavailable"
		effectApplied = false
	} else if idempotency.State == "replay" {
		replayIdempotentResponse(tracked, idempotency.Record)
		outcome = "idempotent_replay"
		effectApplied = false
		effectOrdinal = idempotency.Record.EffectOrdinal
	} else if !s.ready.Load() {
		http.Error(tracked, "unavailable", http.StatusServiceUnavailable)
		outcome = "substitute_unavailable"
	} else {
		decision := s.matchFaultLease(capabilityID, operation, startedAt)
		leaseID = decision.LeaseID
		if decision.ShouldApplyFault {
			outcome = s.applyFaultDecision(tracked, decision)
		} else {
			next(tracked, request)
			outcome = outcomeForStatus(tracked.Status())
		}
	}
	if idempotency.State == "new" {
		s.finishIdempotency(idempotency.Record, tracked)
	}
	finishedAt := s.now().UTC()
	latency := finishedAt.Sub(startedAt)
	if latency < 0 {
		latency = 0
	}
	entry := s.recordInvocation(
		request,
		callOrdinal,
		leaseID,
		capabilityID,
		operation,
		outcome,
		tracked.Status(),
		latency,
		finishedAt,
		effectApplied,
		effectOrdinal,
		evidence,
		idempotency.State,
	)
	if effectApplied {
		s.appendProviderCallback(evidence.CallbackChannelID, entry)
	}
}

func (s *Server) matchFaultLease(
	capabilityID string,
	operation string,
	now time.Time,
) faultDecision {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireFaultLeasesLocked(now)
	leaseID, found := s.activeLeaseByScope[providerScopeKey(capabilityID, operation)]
	if !found {
		return faultDecision{}
	}
	lease := s.leases[leaseID]
	if lease == nil || lease.State != "active" {
		return faultDecision{}
	}
	lease.MatchedCount++
	lease.Version++
	decision := faultDecision{
		LeaseID:          lease.LeaseID,
		Scenario:         lease.Scenario,
		Delay:            time.Duration(lease.Parameters.DelayMillis) * time.Millisecond,
		RetryAfter:       lease.Parameters.RetryAfterSeconds,
		ShouldApplyFault: true,
	}
	if lease.Scenario == "transient_then_success" {
		if lease.RemainingFailures > 0 {
			lease.RemainingFailures--
		} else {
			decision.ShouldApplyFault = false
		}
	}
	if lease.MatchedCount >= lease.MaxMatches {
		s.finalizeFaultLeaseLocked(lease, "max_matches", now)
	}
	return decision
}

func (s *Server) nextCallOrdinal() uint64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.callOrdinal++
	return s.callOrdinal
}

func (s *Server) applyFaultDecision(
	writer http.ResponseWriter,
	decision faultDecision,
) string {
	switch decision.Scenario {
	case "validation":
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return "validation_rejected"
	case "auth":
		http.Error(writer, "unauthorized", http.StatusUnauthorized)
		return "auth_rejected"
	case "delay_timeout":
		s.sleep(decision.Delay)
		http.Error(writer, "provider timeout", http.StatusGatewayTimeout)
		return "timeout"
	case "throttle":
		writer.Header().Set("Retry-After", fmt.Sprint(decision.RetryAfter))
		http.Error(writer, "throttled", http.StatusTooManyRequests)
		return "throttled"
	case "transient_then_success":
		http.Error(writer, "provider transiently unavailable", http.StatusServiceUnavailable)
		return "transient_unavailable"
	case "unavailable":
		http.Error(writer, "provider unavailable", http.StatusServiceUnavailable)
		return "unavailable"
	default:
		http.Error(writer, "provider fault lease invalid", http.StatusInternalServerError)
		return "invalid_fault_lease"
	}
}

func (s *Server) recordInvocation(
	request *http.Request,
	callOrdinal uint64,
	leaseID string,
	capabilityID string,
	operation string,
	outcome string,
	status int,
	latency time.Duration,
	observedAt time.Time,
	effectApplied bool,
	effectOrdinal uint64,
	evidence providerRequestEvidence,
	idempotencyState string,
) InvocationLedgerEntry {
	requestMaterial := strings.Join([]string{
		request.Method,
		request.URL.EscapedPath(),
		request.URL.RawQuery,
		request.Header.Get("X-Request-ID"),
	}, "\n")
	traceMaterial := request.Header.Get("traceparent")
	if traceMaterial == "" {
		traceMaterial = request.Header.Get("X-Trace-ID")
	}
	if traceMaterial == "" {
		traceMaterial = "absent"
	}
	entry := InvocationLedgerEntry{
		LeaseID:              leaseID,
		CapabilityID:         capabilityID,
		Operation:            operation,
		CallOrdinal:          callOrdinal,
		EffectOrdinal:        effectOrdinal,
		RequestDigest:        digestText("request\n" + requestMaterial),
		TraceDigest:          digestText("trace\n" + traceMaterial),
		Outcome:              outcome,
		Status:               status,
		LatencyMillis:        latency.Milliseconds(),
		ObservedAt:           observedAt,
		IdempotencyKeyDigest: evidence.IdempotencyKeyDigest,
		IdempotencyState:     idempotencyState,
		NetworkHostDigest:    evidence.NetworkHostDigest,
		TLSServerNameDigest:  evidence.TLSServerNameDigest,
		TLSVersion:           evidence.TLSVersion,
	}

	s.mu.Lock()
	scope := providerScopeKey(capabilityID, operation)
	s.counts[scope]++
	if effectApplied {
		s.effectCounts[scope]++
	}
	if entry.LeaseID != "" {
		s.counts[providerScopeKey(capabilityID, operation)+".fault_lease_match"]++
	}
	s.ledger = append(s.ledger, entry)
	if len(s.ledger) > maximumInvocationLedgerSize {
		s.ledger = append([]InvocationLedgerEntry(nil), s.ledger[len(s.ledger)-maximumInvocationLedgerSize:]...)
	}
	s.mu.Unlock()
	return entry
}

func (s *Server) expireFaultLeasesLocked(now time.Time) {
	for _, leaseID := range s.activeLeaseByScope {
		lease := s.leases[leaseID]
		if lease != nil && lease.State == "active" && !now.Before(lease.ExpiresAt) {
			s.finalizeFaultLeaseLocked(lease, "expired", now)
		}
	}
}

func (s *Server) finalizeFaultLeaseLocked(
	lease *FaultLease,
	reason string,
	now time.Time,
) {
	if lease == nil || lease.State != "active" {
		return
	}
	delete(s.activeLeaseByScope, providerScopeKey(lease.CapabilityID, lease.Operation))
	lease.Version++
	switch reason {
	case "released":
		lease.State = "released"
	case "expired":
		lease.State = "expired"
	default:
		lease.State = "exhausted"
	}
	receiptMaterial := strings.Join([]string{
		lease.LeaseID,
		lease.CapabilityID,
		lease.Operation,
		reason,
		fmt.Sprint(lease.Version),
		now.Format(time.RFC3339Nano),
	}, "|")
	lease.CleanupReceipt = &FaultCleanupReceipt{
		Status:       "restored",
		Reason:       reason,
		ReceiptRef:   "receipt:provider-fault-cleanup:" + strings.TrimPrefix(digestText(receiptMaterial), "sha256:")[:24],
		LeaseVersion: lease.Version,
		RestoredAt:   now,
	}
}

func providerScopeKey(capabilityID string, operation string) string {
	return capabilityID + "/" + operation
}

func newFaultLeaseID() (string, error) {
	material := make([]byte, 16)
	if _, err := rand.Read(material); err != nil {
		return "", err
	}
	return "fault-" + hex.EncodeToString(material), nil
}

func isSHA256Digest(value string) bool {
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") ||
		value != strings.ToLower(value) {
		return false
	}
	decoded, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil && len(decoded) == sha256.Size
}

func digestText(value string) string {
	digest := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(digest[:])
}

func decodeStrictJSON(
	writer http.ResponseWriter,
	request *http.Request,
	limit int64,
	target any,
) error {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, limit))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		http.Error(writer, "invalid request", http.StatusBadRequest)
		return errors.New("request must contain exactly one JSON document")
	}
	return nil
}

type statusTrackingWriter struct {
	http.ResponseWriter
	status int
}

func (writer *statusTrackingWriter) WriteHeader(status int) {
	if writer.status != 0 {
		return
	}
	writer.status = status
	writer.ResponseWriter.WriteHeader(status)
}

func (writer *statusTrackingWriter) Write(payload []byte) (int, error) {
	if writer.status == 0 {
		writer.WriteHeader(http.StatusOK)
	}
	return writer.ResponseWriter.Write(payload)
}

func (writer *statusTrackingWriter) Flush() {
	if writer.status == 0 {
		writer.WriteHeader(http.StatusOK)
	}
	if flusher, ok := writer.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func (writer *statusTrackingWriter) Status() int {
	if writer.status == 0 {
		return http.StatusOK
	}
	return writer.status
}

func outcomeForStatus(status int) string {
	switch {
	case status >= 200 && status < 400:
		return "success"
	case status >= 400 && status < 500:
		return "provider_rejected"
	default:
		return "provider_failed"
	}
}
