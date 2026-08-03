package application

import (
	"context"
	"errors"
	"time"
)

const rtcMediaQoeWindowHours = 24

var ErrRtcMediaQoeSummaryReaderUnavailable = errors.New("rtc media qoe summary reader is unavailable")

// RtcMediaQoeSummaryReader 是 EventRecord 的专用 named reader。实现只能读取
// rtc_media_qoe 权威事实或其 canonical rollup，禁止委托 generic event summary。
type RtcMediaQoeSummaryReader interface {
	ReadRtcMediaQoeSummary(
		context.Context,
		RtcMediaQoeSummaryQuery,
	) (RtcMediaQoeSummarySlice, error)
}

type RtcMediaQoeSummaryQuery struct {
	From time.Time
	To   time.Time
}

// RtcMediaQoeAggregate 是存储 adapter 返回给统一口径 builder 的强类型聚合行。
// ConnectP95MS 必须由原始 connected connectTimeMs 或可合并 histogram 计算。
type RtcMediaQoeAggregate struct {
	BucketStart          time.Time
	EffectiveSampleCount int64
	MediaConnectedCount  int64
	ConnectP95MS         *float64
	ConnectionLostCount  int64
	ReconnectCount       int64
	GeneratedThrough     *time.Time
}

type RtcMediaQoeHourlyPoint struct {
	BucketStart          string   `json:"bucketStart"`
	Partial              bool     `json:"partial"`
	HasSamples           bool     `json:"hasSamples"`
	EffectiveSampleCount int64    `json:"effectiveSampleCount"`
	MediaConnectedCount  int64    `json:"mediaConnectedCount"`
	MediaConnectedRate   *float64 `json:"mediaConnectedRate"`
	ConnectP95MS         *float64 `json:"connectP95Ms"`
	ConnectionLostCount  int64    `json:"connectionLostCount"`
	ConnectionLostRate   *float64 `json:"connectionLostRate"`
	ReconnectCount       int64    `json:"reconnectCount"`
	GeneratedThrough     *string  `json:"generatedThrough"`
}

type RtcMediaQoeSummarySlice struct {
	HasSamples           bool                     `json:"hasSamples"`
	WindowHours          int                      `json:"windowHours"`
	ActualFrom           string                   `json:"actualFrom"`
	ActualTo             string                   `json:"actualTo"`
	EffectiveSampleCount int64                    `json:"effectiveSampleCount"`
	MediaConnectedCount  int64                    `json:"mediaConnectedCount"`
	MediaConnectedRate   *float64                 `json:"mediaConnectedRate"`
	ConnectP95MS         *float64                 `json:"connectP95Ms"`
	ConnectionLostCount  int64                    `json:"connectionLostCount"`
	ConnectionLostRate   *float64                 `json:"connectionLostRate"`
	ReconnectCount       int64                    `json:"reconnectCount"`
	Series               []RtcMediaQoeHourlyPoint `json:"series"`
	SourceKind           string                   `json:"sourceKind"`
	Freshness            string                   `json:"freshness"`
	GeneratedThrough     *string                  `json:"generatedThrough"`
	LagSeconds           *int64                   `json:"lagSeconds"`
}

// RtcMediaQoeQueryFacade 是 metadata 声明的对象级 query facet。它只依赖
// RtcMediaQoeSummaryReader，不加载 EventRecord 写模型，也不复用 generic summary。
type RtcMediaQoeQueryFacade struct {
	reader RtcMediaQoeSummaryReader
	now    func() time.Time
}

func NewRtcMediaQoeQueryFacade(
	reader RtcMediaQoeSummaryReader,
) *RtcMediaQoeQueryFacade {
	return NewRtcMediaQoeQueryFacadeWithClock(reader, time.Now)
}

func NewRtcMediaQoeQueryFacadeWithClock(
	reader RtcMediaQoeSummaryReader,
	now func() time.Time,
) *RtcMediaQoeQueryFacade {
	if reader == nil {
		panic("rtc media QoE query facade requires reader")
	}
	if now == nil {
		panic("rtc media QoE query facade requires clock")
	}
	return &RtcMediaQoeQueryFacade{reader: reader, now: now}
}

func (f *RtcMediaQoeQueryFacade) Get24HourSummary(
	ctx context.Context,
) (RtcMediaQoeSummarySlice, error) {
	now := f.now().UTC()
	currentBucket := now.Truncate(time.Hour)
	return f.reader.ReadRtcMediaQoeSummary(ctx, RtcMediaQoeSummaryQuery{
		From: currentBucket.Add(-(rtcMediaQoeWindowHours - 1) * time.Hour),
		To:   now,
	})
}

func (s *TelemetryService) GetRtcMediaQoeSummary(
	ctx context.Context,
) (RtcMediaQoeSummarySlice, error) {
	if s.rtcMediaQoe == nil {
		return RtcMediaQoeSummarySlice{}, ErrRtcMediaQoeSummaryReaderUnavailable
	}
	return NewRtcMediaQoeQueryFacadeWithClock(
		s.rtcMediaQoe,
		s.now,
	).Get24HourSummary(ctx)
}

// BuildRtcMediaQoeSummary 统一 Elasticsearch 与 local_contract memory reader 的分母、空值和缺桶语义。
// 空桶保留 count=0，但所有 rate/P95 都为 null，不会合成 0% 成功率。
func BuildRtcMediaQoeSummary(
	query RtcMediaQoeSummaryQuery,
	hourly []RtcMediaQoeAggregate,
	total RtcMediaQoeAggregate,
	sourceKind string,
) RtcMediaQoeSummarySlice {
	from := query.From.UTC().Truncate(time.Hour)
	to := query.To.UTC()
	byBucket := make(map[time.Time]RtcMediaQoeAggregate, len(hourly))
	for _, row := range hourly {
		byBucket[row.BucketStart.UTC().Truncate(time.Hour)] = row
	}
	series := make([]RtcMediaQoeHourlyPoint, 0, rtcMediaQoeWindowHours)
	currentBucket := to.Truncate(time.Hour)
	for index := 0; index < rtcMediaQoeWindowHours; index++ {
		bucket := from.Add(time.Duration(index) * time.Hour)
		row := byBucket[bucket]
		point := RtcMediaQoeHourlyPoint{
			BucketStart:          bucket.Format(time.RFC3339Nano),
			Partial:              bucket.Equal(currentBucket),
			HasSamples:           row.EffectiveSampleCount > 0,
			EffectiveSampleCount: row.EffectiveSampleCount,
			MediaConnectedCount:  row.MediaConnectedCount,
			MediaConnectedRate:   ratio(row.MediaConnectedCount, row.EffectiveSampleCount),
			ConnectP95MS:         row.ConnectP95MS,
			ConnectionLostCount:  row.ConnectionLostCount,
			ConnectionLostRate:   ratio(row.ConnectionLostCount, row.MediaConnectedCount),
			ReconnectCount:       row.ReconnectCount,
			GeneratedThrough:     formatOptionalTime(row.GeneratedThrough),
		}
		series = append(series, point)
	}

	hasSamples := total.EffectiveSampleCount > 0
	freshness := "no_samples"
	if hasSamples {
		freshness = "near_realtime"
	}
	generatedThrough := formatOptionalTime(total.GeneratedThrough)
	var lagSeconds *int64
	if total.GeneratedThrough != nil {
		lag := int64(to.Sub(total.GeneratedThrough.UTC()).Seconds())
		if lag < 0 {
			lag = 0
		}
		lagSeconds = &lag
	}
	return RtcMediaQoeSummarySlice{
		HasSamples:           hasSamples,
		WindowHours:          rtcMediaQoeWindowHours,
		ActualFrom:           from.Format(time.RFC3339Nano),
		ActualTo:             to.Format(time.RFC3339Nano),
		EffectiveSampleCount: total.EffectiveSampleCount,
		MediaConnectedCount:  total.MediaConnectedCount,
		MediaConnectedRate:   ratio(total.MediaConnectedCount, total.EffectiveSampleCount),
		ConnectP95MS:         total.ConnectP95MS,
		ConnectionLostCount:  total.ConnectionLostCount,
		ConnectionLostRate:   ratio(total.ConnectionLostCount, total.MediaConnectedCount),
		ReconnectCount:       total.ReconnectCount,
		Series:               series,
		SourceKind:           sourceKind,
		Freshness:            freshness,
		GeneratedThrough:     generatedThrough,
		LagSeconds:           lagSeconds,
	}
}

func ratio(numerator, denominator int64) *float64 {
	if denominator <= 0 {
		return nil
	}
	value := float64(numerator) / float64(denominator)
	return &value
}

func formatOptionalTime(value *time.Time) *string {
	if value == nil {
		return nil
	}
	formatted := value.UTC().Format(time.RFC3339Nano)
	return &formatted
}
