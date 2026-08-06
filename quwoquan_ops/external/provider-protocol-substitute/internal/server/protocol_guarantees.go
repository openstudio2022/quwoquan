package server

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	maximumProviderRequestBytes = 4 << 20
	maximumCallbackChannelTTL   = 300
	maximumCallbackEvents       = 1000
	maximumIdempotencyRecords   = 2048
	idempotencyRecordTTL        = 10 * time.Minute
	idempotencyHeader           = "Idempotency-Key"
	callbackChannelHeader       = "X-Provider-Callback-Channel"
)

var (
	idempotencyKeyPattern  = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]{15,127}$`)
	callbackChannelPattern = regexp.MustCompile(`^callback-[0-9a-f]{32}$`)
)

type providerRequestContextKey struct{}

type providerRequestEvidence struct {
	Fingerprint          string
	IdempotencyKeyDigest string
	CallbackChannelID    string
	NetworkHostDigest    string
	TLSServerNameDigest  string
	TLSVersion           string
}

type idempotencyRecord struct {
	Fingerprint   string
	EffectOrdinal uint64
	Status        int
	Headers       http.Header
	Body          []byte
	Ready         chan struct{}
	ExpiresAt     time.Time
}

type ProviderCallbackEvent struct {
	Sequence      uint64    `json:"sequence"`
	CapabilityID  string    `json:"capabilityId"`
	Operation     string    `json:"operation"`
	CallOrdinal   uint64    `json:"callOrdinal"`
	EffectOrdinal uint64    `json:"effectOrdinal"`
	RequestDigest string    `json:"requestDigest"`
	TraceDigest   string    `json:"traceDigest"`
	Outcome       string    `json:"outcome"`
	Status        int       `json:"status"`
	ObservedAt    time.Time `json:"observedAt"`
}

type CallbackCleanupReceipt struct {
	Status         string    `json:"status"`
	Reason         string    `json:"reason"`
	ReceiptRef     string    `json:"receiptRef"`
	ChannelVersion uint64    `json:"channelVersion"`
	RestoredAt     time.Time `json:"restoredAt"`
}

type CallbackChannel struct {
	ChannelID                string                  `json:"channelId"`
	Environment              string                  `json:"environment"`
	Target                   string                  `json:"target"`
	ConfigurationDigest      string                  `json:"configurationDigest"`
	RuntimeCompositionDigest string                  `json:"runtimeCompositionDigest"`
	CapabilityID             string                  `json:"capabilityId"`
	Operation                string                  `json:"operation"`
	Owner                    string                  `json:"owner"`
	Version                  uint64                  `json:"version"`
	ActivatedAt              time.Time               `json:"activatedAt"`
	ExpiresAt                time.Time               `json:"expiresAt"`
	MaxCallbacks             uint64                  `json:"maxCallbacks"`
	State                    string                  `json:"state"`
	Events                   []ProviderCallbackEvent `json:"events"`
	CleanupReceipt           *CallbackCleanupReceipt `json:"cleanupReceipt,omitempty"`
}

type acquireCallbackChannelRequest struct {
	Environment              string `json:"environment"`
	Target                   string `json:"target"`
	ConfigurationDigest      string `json:"configurationDigest"`
	RuntimeCompositionDigest string `json:"runtimeCompositionDigest"`
	CapabilityID             string `json:"capabilityId"`
	Operation                string `json:"operation"`
	Owner                    string `json:"owner"`
	TTLSeconds               int    `json:"ttlSeconds"`
	MaxCallbacks             uint64 `json:"maxCallbacks"`
}

type releaseCallbackChannelRequest struct {
	Owner           string `json:"owner"`
	ExpectedVersion uint64 `json:"expectedVersion"`
}

type idempotencyDecision struct {
	State  string
	Record *idempotencyRecord
}

func (s *Server) prepareProviderRequest(
	writer http.ResponseWriter,
	request *http.Request,
) (*http.Request, bool) {
	body, err := io.ReadAll(http.MaxBytesReader(writer, request.Body, maximumProviderRequestBytes+1))
	if err != nil || len(body) > maximumProviderRequestBytes {
		http.Error(writer, "invalid request", http.StatusRequestEntityTooLarge)
		return nil, false
	}
	request.Body = io.NopCloser(bytes.NewReader(body))
	idempotencyKey := strings.TrimSpace(request.Header.Get(idempotencyHeader))
	if idempotencyKey != "" && !idempotencyKeyPattern.MatchString(idempotencyKey) {
		http.Error(writer, "invalid idempotency key", http.StatusBadRequest)
		return nil, false
	}
	callbackChannelID := strings.TrimSpace(request.Header.Get(callbackChannelHeader))
	if callbackChannelID != "" && !callbackChannelPattern.MatchString(callbackChannelID) {
		http.Error(writer, "invalid callback channel", http.StatusBadRequest)
		return nil, false
	}
	host := request.Host
	if parsedHost, _, splitErr := net.SplitHostPort(host); splitErr == nil {
		host = parsedHost
	}
	evidence := providerRequestEvidence{
		Fingerprint: digestText(strings.Join([]string{
			request.Method,
			request.URL.EscapedPath(),
			request.URL.RawQuery,
			digestText(string(body)),
		}, "\n")),
		CallbackChannelID: callbackChannelID,
		NetworkHostDigest: digestText("dns\n" + strings.ToLower(host)),
	}
	if idempotencyKey != "" {
		evidence.IdempotencyKeyDigest = digestText("idempotency\n" + idempotencyKey)
	}
	if request.TLS != nil {
		evidence.TLSServerNameDigest = digestText(
			"dns\n" + strings.ToLower(request.TLS.ServerName),
		)
		evidence.TLSVersion = tlsVersionName(request.TLS.Version)
	}
	prepared := request.WithContext(
		context.WithValue(request.Context(), providerRequestContextKey{}, evidence),
	)
	prepared.Body = request.Body
	return prepared, true
}

func requestEvidence(request *http.Request) providerRequestEvidence {
	value, _ := request.Context().Value(providerRequestContextKey{}).(providerRequestEvidence)
	return value
}

func tlsVersionName(version uint16) string {
	switch version {
	case tls.VersionTLS13:
		return "TLSv1.3"
	case tls.VersionTLS12:
		return "TLSv1.2"
	default:
		return fmt.Sprintf("TLS-0x%04x", version)
	}
}

func (s *Server) beginIdempotency(
	scope string,
	evidence providerRequestEvidence,
	effectOrdinal uint64,
) idempotencyDecision {
	if evidence.IdempotencyKeyDigest == "" {
		return idempotencyDecision{State: "none"}
	}
	key := scope + "/" + evidence.IdempotencyKeyDigest
	s.mu.Lock()
	s.expireIdempotencyRecordsLocked(s.now().UTC())
	existing := s.idempotencyRecords[key]
	if existing == nil {
		if len(s.idempotencyRecords) >= maximumIdempotencyRecords {
			s.mu.Unlock()
			return idempotencyDecision{State: "capacity"}
		}
		record := &idempotencyRecord{
			Fingerprint:   evidence.Fingerprint,
			EffectOrdinal: effectOrdinal,
			Ready:         make(chan struct{}),
			ExpiresAt:     s.now().UTC().Add(idempotencyRecordTTL),
		}
		s.idempotencyRecords[key] = record
		s.mu.Unlock()
		return idempotencyDecision{State: "new", Record: record}
	}
	s.mu.Unlock()
	if existing.Fingerprint != evidence.Fingerprint {
		return idempotencyDecision{State: "conflict", Record: existing}
	}
	<-existing.Ready
	return idempotencyDecision{State: "replay", Record: existing}
}

func (s *Server) expireIdempotencyRecordsLocked(now time.Time) {
	for key, record := range s.idempotencyRecords {
		if record == nil || now.Before(record.ExpiresAt) {
			continue
		}
		select {
		case <-record.Ready:
			delete(s.idempotencyRecords, key)
		default:
		}
	}
}

func (s *Server) finishIdempotency(record *idempotencyRecord, captured *responseCapture) {
	if record == nil {
		return
	}
	s.mu.Lock()
	record.Status = captured.Status()
	record.Headers = captured.Header().Clone()
	record.Body = append([]byte(nil), captured.body.Bytes()...)
	close(record.Ready)
	s.mu.Unlock()
}

func replayIdempotentResponse(writer http.ResponseWriter, record *idempotencyRecord) {
	for key, values := range record.Headers {
		for _, value := range values {
			writer.Header().Add(key, value)
		}
	}
	writer.WriteHeader(record.Status)
	_, _ = writer.Write(record.Body)
}

func (s *Server) acquireCallbackChannel(writer http.ResponseWriter, request *http.Request) {
	var payload acquireCallbackChannelRequest
	if err := decodeStrictJSON(writer, request, 16<<10, &payload); err != nil {
		return
	}
	if err := s.validateCallbackChannelRequest(payload); err != nil {
		http.Error(writer, "invalid callback channel request", http.StatusBadRequest)
		return
	}
	channelID, err := newCallbackChannelID()
	if err != nil {
		http.Error(writer, "callback channel unavailable", http.StatusInternalServerError)
		return
	}
	now := s.now().UTC()
	channel := &CallbackChannel{
		ChannelID:                channelID,
		Environment:              s.environment,
		Target:                   s.target,
		ConfigurationDigest:      s.configurationDigest,
		RuntimeCompositionDigest: s.runtimeCompositionDigest,
		CapabilityID:             payload.CapabilityID,
		Operation:                payload.Operation,
		Owner:                    payload.Owner,
		Version:                  1,
		ActivatedAt:              now,
		ExpiresAt:                now.Add(time.Duration(payload.TTLSeconds) * time.Second),
		MaxCallbacks:             payload.MaxCallbacks,
		State:                    "active",
		Events:                   []ProviderCallbackEvent{},
	}
	s.mu.Lock()
	s.expireCallbackChannelsLocked(now)
	if len(s.callbackChannels) >= maximumInvocationLedgerSize {
		s.mu.Unlock()
		http.Error(writer, "callback channel capacity unavailable", http.StatusServiceUnavailable)
		return
	}
	s.callbackChannels[channelID] = channel
	response := cloneCallbackChannel(channel)
	s.mu.Unlock()
	writeJSON(writer, http.StatusCreated, response)
}

func (s *Server) readCallbackChannel(writer http.ResponseWriter, request *http.Request) {
	channelID := strings.TrimSpace(request.PathValue("channelId"))
	if !callbackChannelPattern.MatchString(channelID) {
		http.Error(writer, "invalid callback channel identity", http.StatusBadRequest)
		return
	}
	s.mu.Lock()
	s.expireCallbackChannelsLocked(s.now().UTC())
	channel := s.callbackChannels[channelID]
	if channel == nil {
		s.mu.Unlock()
		http.Error(writer, "callback channel not found", http.StatusNotFound)
		return
	}
	response := cloneCallbackChannel(channel)
	s.mu.Unlock()
	writeJSON(writer, http.StatusOK, response)
}

func (s *Server) releaseCallbackChannel(writer http.ResponseWriter, request *http.Request) {
	channelID := strings.TrimSpace(request.PathValue("channelId"))
	if !callbackChannelPattern.MatchString(channelID) {
		http.Error(writer, "invalid callback channel identity", http.StatusBadRequest)
		return
	}
	var payload releaseCallbackChannelRequest
	if err := decodeStrictJSON(writer, request, 4096, &payload); err != nil {
		return
	}
	s.mu.Lock()
	s.expireCallbackChannelsLocked(s.now().UTC())
	channel := s.callbackChannels[channelID]
	if channel == nil {
		s.mu.Unlock()
		http.Error(writer, "callback channel not found", http.StatusNotFound)
		return
	}
	if channel.State != "active" || channel.Owner != payload.Owner ||
		channel.Version != payload.ExpectedVersion {
		s.mu.Unlock()
		http.Error(writer, "callback channel release conflict", http.StatusConflict)
		return
	}
	s.finalizeCallbackChannelLocked(channel, "released", s.now().UTC())
	response := cloneCallbackChannel(channel)
	s.mu.Unlock()
	writeJSON(writer, http.StatusOK, response)
}

func (s *Server) validateCallbackChannelRequest(payload acquireCallbackChannelRequest) error {
	if payload.Environment != s.environment || payload.Target != s.target ||
		payload.ConfigurationDigest != s.configurationDigest ||
		payload.RuntimeCompositionDigest != s.runtimeCompositionDigest {
		return errors.New("callback channel runtime identity mismatch")
	}
	operations := canonicalProviderScopes[payload.CapabilityID]
	if operations == nil {
		return errors.New("callback channel capability is not canonical")
	}
	if _, found := operations[payload.Operation]; !found {
		return errors.New("callback channel operation is not canonical")
	}
	if !faultOwnerPattern.MatchString(payload.Owner) || payload.TTLSeconds < 1 ||
		payload.TTLSeconds > maximumCallbackChannelTTL || payload.MaxCallbacks < 1 ||
		payload.MaxCallbacks > maximumCallbackEvents {
		return errors.New("callback channel bound is invalid")
	}
	return nil
}

func (s *Server) validateCallbackChannel(
	channelID string,
	capabilityID string,
	operation string,
) bool {
	if channelID == "" {
		return true
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireCallbackChannelsLocked(s.now().UTC())
	channel := s.callbackChannels[channelID]
	return channel != nil && channel.State == "active" &&
		channel.CapabilityID == capabilityID && channel.Operation == operation
}

func (s *Server) appendProviderCallback(channelID string, entry InvocationLedgerEntry) {
	if channelID == "" {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireCallbackChannelsLocked(s.now().UTC())
	channel := s.callbackChannels[channelID]
	if channel == nil || channel.State != "active" ||
		channel.CapabilityID != entry.CapabilityID || channel.Operation != entry.Operation {
		return
	}
	channel.Events = append(channel.Events, ProviderCallbackEvent{
		Sequence:      uint64(len(channel.Events) + 1),
		CapabilityID:  entry.CapabilityID,
		Operation:     entry.Operation,
		CallOrdinal:   entry.CallOrdinal,
		EffectOrdinal: entry.EffectOrdinal,
		RequestDigest: entry.RequestDigest,
		TraceDigest:   entry.TraceDigest,
		Outcome:       entry.Outcome,
		Status:        entry.Status,
		ObservedAt:    entry.ObservedAt,
	})
	channel.Version++
	if uint64(len(channel.Events)) >= channel.MaxCallbacks {
		s.finalizeCallbackChannelLocked(channel, "max_callbacks", s.now().UTC())
	}
}

func (s *Server) expireCallbackChannelsLocked(now time.Time) {
	for channelID, channel := range s.callbackChannels {
		if channel.State == "active" && !now.Before(channel.ExpiresAt) {
			s.finalizeCallbackChannelLocked(channel, "expired", now)
		}
		if channel.State != "active" && channel.CleanupReceipt != nil &&
			now.Sub(channel.CleanupReceipt.RestoredAt) >= idempotencyRecordTTL {
			delete(s.callbackChannels, channelID)
		}
	}
}

func (s *Server) finalizeCallbackChannelLocked(
	channel *CallbackChannel,
	reason string,
	now time.Time,
) {
	if channel == nil || channel.State != "active" {
		return
	}
	channel.Version++
	switch reason {
	case "released":
		channel.State = "released"
	case "expired":
		channel.State = "expired"
	default:
		channel.State = "exhausted"
	}
	receiptMaterial := strings.Join([]string{
		channel.ChannelID,
		channel.CapabilityID,
		channel.Operation,
		reason,
		fmt.Sprint(channel.Version),
		now.Format(time.RFC3339Nano),
	}, "|")
	channel.CleanupReceipt = &CallbackCleanupReceipt{
		Status: "restored",
		Reason: reason,
		ReceiptRef: "receipt:provider-callback-cleanup:" +
			strings.TrimPrefix(digestText(receiptMaterial), "sha256:")[:24],
		ChannelVersion: channel.Version,
		RestoredAt:     now,
	}
}

func cloneCallbackChannel(channel *CallbackChannel) CallbackChannel {
	copy := *channel
	copy.Events = append([]ProviderCallbackEvent(nil), channel.Events...)
	if channel.CleanupReceipt != nil {
		receipt := *channel.CleanupReceipt
		copy.CleanupReceipt = &receipt
	}
	return copy
}

func newCallbackChannelID() (string, error) {
	material := make([]byte, 16)
	if _, err := rand.Read(material); err != nil {
		return "", err
	}
	return "callback-" + hex.EncodeToString(material), nil
}

func sortedCallbackChannels(channels map[string]*CallbackChannel) []CallbackChannel {
	result := make([]CallbackChannel, 0, len(channels))
	for _, channel := range channels {
		result = append(result, cloneCallbackChannel(channel))
	}
	sort.Slice(result, func(left, right int) bool {
		return result[left].ChannelID < result[right].ChannelID
	})
	return result
}

type responseCapture struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (writer *responseCapture) WriteHeader(status int) {
	if writer.status != 0 {
		return
	}
	writer.status = status
	writer.ResponseWriter.WriteHeader(status)
}

func (writer *responseCapture) Write(payload []byte) (int, error) {
	if writer.status == 0 {
		writer.WriteHeader(http.StatusOK)
	}
	_, _ = writer.body.Write(payload)
	return writer.ResponseWriter.Write(payload)
}

func (writer *responseCapture) Flush() {
	if writer.status == 0 {
		writer.WriteHeader(http.StatusOK)
	}
	if flusher, ok := writer.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func (writer *responseCapture) Status() int {
	if writer.status == 0 {
		return http.StatusOK
	}
	return writer.status
}
