package redisstore

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/domain/model"
)

const (
	presenceKeyPrefix = "presence:persona:"
	maximumCASRetries = 8
)

var (
	presenceStaleFieldsRemovedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "realtime_presence_stale_fields_removed_total",
			Help: "Stale persona-device presence hash fields removed by the named reader.",
		},
	)
	presenceViewDeviceCount = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "realtime_presence_view_device_count",
			Help:    "Fresh device count returned by PresenceView.",
			Buckets: []float64{0, 1, 2, 3, 5, 8, 16},
		},
	)
)

type Store struct{ client rtredis.Client }

func NewStore(client rtredis.Client) (*Store, error) {
	if client == nil {
		return nil, errors.New("presence redis store requires a client")
	}
	return &Store{client: client}, nil
}

func (store *Store) UpsertIfNewer(
	ctx context.Context,
	candidate model.Device,
) (bool, error) {
	if err := candidate.Validate(); err != nil {
		return false, err
	}
	encoded, err := json.Marshal(candidate)
	if err != nil {
		return false, err
	}
	key := presenceKeyPrefix + candidate.PersonaID
	for attempt := 0; attempt < maximumCASRetries; attempt++ {
		current, getErr := store.client.HGet(ctx, key, candidate.DeviceID)
		var expected *string
		if getErr == nil {
			var existing model.Device
			if json.Unmarshal([]byte(current), &existing) == nil &&
				existing.Validate() == nil {
				if existing.Sequence > candidate.Sequence ||
					(existing.Sequence == candidate.Sequence &&
						existing.ConnectionID != candidate.ConnectionID) {
					return false, nil
				}
			}
			expected = &current
		} else if !errors.Is(getErr, rtredis.ErrKeyNotFound) {
			return false, getErr
		}
		replacement := string(encoded)
		swapped, swapErr := rtredis.CompareAndSwapHashField(
			ctx,
			store.client,
			key,
			candidate.DeviceID,
			expected,
			&replacement,
			model.ProjectionTTL,
		)
		if swapErr != nil {
			return false, swapErr
		}
		if swapped {
			return true, nil
		}
	}
	return false, errors.New("presence projection compare-and-swap contention")
}

func (store *Store) DeleteConnection(
	ctx context.Context,
	personaID string,
	deviceID string,
	connectionID string,
	sequence int64,
) (bool, error) {
	key := presenceKeyPrefix + strings.TrimSpace(personaID)
	field := strings.TrimSpace(deviceID)
	for attempt := 0; attempt < maximumCASRetries; attempt++ {
		current, err := store.client.HGet(ctx, key, field)
		if errors.Is(err, rtredis.ErrKeyNotFound) {
			return false, nil
		}
		if err != nil {
			return false, err
		}
		var existing model.Device
		if json.Unmarshal([]byte(current), &existing) != nil ||
			existing.ConnectionID != strings.TrimSpace(connectionID) ||
			existing.Sequence > sequence {
			return false, nil
		}
		swapped, swapErr := rtredis.CompareAndSwapHashField(
			ctx,
			store.client,
			key,
			field,
			&current,
			nil,
			0,
		)
		if swapErr != nil {
			return false, swapErr
		}
		if swapped {
			return true, nil
		}
	}
	return false, errors.New("presence deletion compare-and-swap contention")
}

func (store *Store) ReadPresence(
	ctx context.Context,
	personaID string,
	now time.Time,
) (model.View, error) {
	personaID = strings.TrimSpace(personaID)
	view := model.View{PersonaID: personaID, Devices: []model.Device{}}
	entries, err := store.client.HGetAll(ctx, presenceKeyPrefix+personaID)
	if err != nil && !errors.Is(err, rtredis.ErrKeyNotFound) {
		return view, err
	}
	for field, encoded := range entries {
		var device model.Device
		valid := json.Unmarshal([]byte(encoded), &device) == nil &&
			device.Validate() == nil &&
			device.PersonaID == personaID &&
			device.DeviceID == strings.TrimSpace(field)
		if !valid || now.UTC().Sub(device.LastHeartbeatAt) > model.StaleAfter ||
			!device.ExpiresAt.After(now.UTC()) {
			current := encoded
			removed, removeErr := rtredis.CompareAndSwapHashField(
				ctx,
				store.client,
				presenceKeyPrefix+personaID,
				field,
				&current,
				nil,
				0,
			)
			if removeErr != nil {
				return view, removeErr
			}
			if removed {
				presenceStaleFieldsRemovedTotal.Inc()
			}
			continue
		}
		view.Devices = append(view.Devices, device)
	}
	sort.Slice(view.Devices, func(i, j int) bool {
		return view.Devices[i].DeviceID < view.Devices[j].DeviceID
	})
	presenceViewDeviceCount.Observe(float64(len(view.Devices)))
	return view, nil
}

func (store *Store) RemoveConnection(
	ctx context.Context,
	accountID string,
	personaID string,
	deviceID string,
	connectionID string,
) error {
	key := presenceKeyPrefix + strings.TrimSpace(personaID)
	field := strings.TrimSpace(deviceID)
	for attempt := 0; attempt < maximumCASRetries; attempt++ {
		current, err := store.client.HGet(ctx, key, field)
		if errors.Is(err, rtredis.ErrKeyNotFound) {
			return nil
		}
		if err != nil {
			return err
		}
		var existing model.Device
		if json.Unmarshal([]byte(current), &existing) != nil ||
			existing.AccountID != strings.TrimSpace(accountID) ||
			existing.ConnectionID != strings.TrimSpace(connectionID) {
			return nil
		}
		swapped, swapErr := rtredis.CompareAndSwapHashField(
			ctx, store.client, key, field, &current, nil, 0,
		)
		if swapErr != nil {
			return swapErr
		}
		if swapped {
			return nil
		}
	}
	return errors.New("presence connection revocation contention")
}

func (store *Store) RemoveAccount(
	ctx context.Context,
	accountID string,
	personaIDs []string,
) error {
	seen := make(map[string]struct{}, len(personaIDs))
	for _, personaID := range personaIDs {
		personaID = strings.TrimSpace(personaID)
		if personaID == "" {
			continue
		}
		if _, duplicate := seen[personaID]; duplicate {
			continue
		}
		seen[personaID] = struct{}{}
		entries, err := store.client.HGetAll(ctx, presenceKeyPrefix+personaID)
		if err != nil && !errors.Is(err, rtredis.ErrKeyNotFound) {
			return err
		}
		for deviceID, encoded := range entries {
			var existing model.Device
			if json.Unmarshal([]byte(encoded), &existing) != nil ||
				existing.AccountID != strings.TrimSpace(accountID) {
				continue
			}
			current := encoded
			_, err = rtredis.CompareAndSwapHashField(
				ctx,
				store.client,
				presenceKeyPrefix+personaID,
				deviceID,
				&current,
				nil,
				0,
			)
			if err != nil {
				return err
			}
		}
	}
	return nil
}
