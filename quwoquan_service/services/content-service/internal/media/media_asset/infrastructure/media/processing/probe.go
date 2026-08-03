package processing

import (
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"strings"
)

// VideoProbe is the parsed visual-media subset of
// `ffprobe -show_streams -show_format` the image/video pipeline decides on.
type VideoProbe struct {
	DurationMs  int64
	Width       int
	Height      int
	VideoCodec  string
	PixelFormat string
	AudioCodec  string
	HasVideo    bool
	HasAudio    bool
	FrameRate   float64
	FormatNames []string
}

type ffprobeOutput struct {
	Streams []ffprobeStream `json:"streams"`
	Format  ffprobeFormat   `json:"format"`
}

type ffprobeStream struct {
	CodecType    string `json:"codec_type"`
	CodecName    string `json:"codec_name"`
	Width        int    `json:"width"`
	Height       int    `json:"height"`
	PixelFormat  string `json:"pix_fmt"`
	AvgFrameRate string `json:"avg_frame_rate"`
	RFrameRate   string `json:"r_frame_rate"`
	Duration     string `json:"duration"`
}

type ffprobeFormat struct {
	FormatName string `json:"format_name"`
	Duration   string `json:"duration"`
}

// ParseFFprobeOutput turns raw ffprobe JSON into a typed probe. It is a pure
// function so malformed-media decision rules stay unit-testable.
func ParseFFprobeOutput(raw []byte) (VideoProbe, error) {
	var output ffprobeOutput
	if err := json.Unmarshal(raw, &output); err != nil {
		return VideoProbe{}, fmt.Errorf("parse ffprobe output: %w", err)
	}
	probe := VideoProbe{
		FormatNames: splitFormatNames(output.Format.FormatName),
	}
	probe.DurationMs = parseDurationMs(output.Format.Duration)
	for _, stream := range output.Streams {
		switch strings.ToLower(strings.TrimSpace(stream.CodecType)) {
		case "video":
			if probe.HasVideo {
				continue
			}
			probe.HasVideo = true
			probe.VideoCodec = strings.ToLower(strings.TrimSpace(stream.CodecName))
			probe.PixelFormat = strings.ToLower(strings.TrimSpace(stream.PixelFormat))
			probe.Width = stream.Width
			probe.Height = stream.Height
			probe.FrameRate = parseFrameRate(stream.AvgFrameRate)
			if probe.FrameRate <= 0 {
				probe.FrameRate = parseFrameRate(stream.RFrameRate)
			}
			if probe.DurationMs <= 0 {
				probe.DurationMs = parseDurationMs(stream.Duration)
			}
		case "audio":
			if probe.HasAudio {
				continue
			}
			probe.HasAudio = true
			probe.AudioCodec = strings.ToLower(strings.TrimSpace(stream.CodecName))
		}
	}
	return probe, nil
}

func splitFormatNames(value string) []string {
	parts := strings.Split(strings.TrimSpace(value), ",")
	names := make([]string, 0, len(parts))
	for _, part := range parts {
		if part = strings.ToLower(strings.TrimSpace(part)); part != "" {
			names = append(names, part)
		}
	}
	return names
}

func parseDurationMs(value string) int64 {
	seconds, err := strconv.ParseFloat(strings.TrimSpace(value), 64)
	if err != nil || seconds <= 0 || math.IsNaN(seconds) || math.IsInf(seconds, 0) {
		return 0
	}
	return int64(math.Round(seconds * 1000))
}

func parseFrameRate(value string) float64 {
	value = strings.TrimSpace(value)
	if value == "" || value == "0/0" {
		return 0
	}
	numerator, denominator, found := strings.Cut(value, "/")
	if !found {
		rate, err := strconv.ParseFloat(value, 64)
		if err != nil {
			return 0
		}
		return rate
	}
	top, err := strconv.ParseFloat(numerator, 64)
	if err != nil {
		return 0
	}
	bottom, err := strconv.ParseFloat(denominator, 64)
	if err != nil || bottom == 0 {
		return 0
	}
	return top / bottom
}
