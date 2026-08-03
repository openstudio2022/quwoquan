package post

import (
	"math"
	"regexp"
	"sort"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

const capturePhotographyTagRoot = "Topic/摄影"

var captureDisclosureGroups = map[string]struct{}{
	"gear": {}, "parameters": {}, "place": {}, "time": {},
}

var captureLensZoomPattern = regexp.MustCompile(`\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*MM`)
var captureLensPrimePattern = regexp.MustCompile(`\d+(?:\.\d+)?\s*MM`)

func validateCaptureDisclosure(post *postmodel.Post) error {
	if post == nil {
		return nil
	}
	seen := make(map[string]struct{}, len(post.CaptureDisclosure))
	normalized := make([]string, 0, len(post.CaptureDisclosure))
	for _, raw := range post.CaptureDisclosure {
		group := strings.ToLower(strings.TrimSpace(raw))
		if _, allowed := captureDisclosureGroups[group]; !allowed {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"拍摄信息披露选项不合法",
				"captureDisclosure contains an unsupported group",
			)
		}
		if _, duplicate := seen[group]; duplicate {
			continue
		}
		seen[group] = struct{}{}
		normalized = append(normalized, group)
	}
	sort.Strings(normalized)
	post.CaptureDisclosure = normalized
	for _, tag := range post.TagRefs {
		if isCaptureDerivedTag(strings.TrimSpace(tag)) {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"拍摄信息不能作为公开标签提交",
				"capture-derived tags are server-owned recommendation features",
			)
		}
	}
	return nil
}

// projectCaptureMetadataFeatures is the only service-side projection from the
// creator-disclosed MediaAsset EXIF snapshot into the photography taxonomy.
// It always removes the owned subtrees first, so disabling a disclosure group
// withdraws the whole derived subtree instead of leaving stale client tags.
func projectCaptureMetadataFeatures(
	post *postmodel.Post,
	assets map[string]MediaAssetBindingSlice,
	boundAssetIDs []string,
) {
	if post == nil {
		return
	}
	disclosed := make(map[string]bool, len(post.CaptureDisclosure))
	for _, group := range post.CaptureDisclosure {
		if _, allowed := captureDisclosureGroups[group]; allowed {
			disclosed[group] = true
		}
	}
	features := make(map[string]struct{})
	for _, assetID := range boundAssetIDs {
		asset, ok := assets[assetID]
		if !ok || !strings.EqualFold(asset.MediaType, "image") {
			continue
		}
		for _, tag := range deriveCaptureMetadataTags(asset.CaptureMetadata, disclosed) {
			features[tag] = struct{}{}
		}
	}
	post.CaptureFeatureRefs = make([]string, 0, len(features))
	for feature := range features {
		post.CaptureFeatureRefs = append(post.CaptureFeatureRefs, feature)
	}
	sort.Strings(post.CaptureFeatureRefs)
}

func isCaptureDerivedTag(tag string) bool {
	return strings.HasPrefix(tag, capturePhotographyTagRoot+"/器材/") ||
		strings.HasPrefix(tag, capturePhotographyTagRoot+"/拍摄参数/") ||
		strings.HasPrefix(tag, capturePhotographyTagRoot+"/光线条件/")
}

func deriveCaptureMetadataTags(
	metadata mediamodel.CaptureMetadata,
	disclosed map[string]bool,
) []string {
	tags := make(map[string]struct{})
	if disclosed["gear"] {
		if body := captureBodyType(metadata); body != "" {
			tags[capturePhotographyTagRoot+"/器材/机身类型/"+body] = struct{}{}
		}
		for _, lens := range captureLensTypes(metadata.LensModel) {
			tags[capturePhotographyTagRoot+"/器材/镜头类型/"+lens] = struct{}{}
		}
	}
	if disclosed["parameters"] {
		if focal := captureFocalRange(metadata.FocalLengthMM); focal != "" {
			tags[capturePhotographyTagRoot+"/拍摄参数/焦段/"+focal] = struct{}{}
		}
		if value := metadata.ShutterSpeedSeconds; value != nil {
			switch {
			case *value >= 1:
				tags[capturePhotographyTagRoot+"/拍摄参数/快门/长曝光"] = struct{}{}
			case *value >= 1.0/15.0:
				tags[capturePhotographyTagRoot+"/拍摄参数/快门/慢门"] = struct{}{}
			case *value <= 1.0/1000.0:
				tags[capturePhotographyTagRoot+"/拍摄参数/快门/高速快门"] = struct{}{}
			}
		}
		if value := metadata.ApertureFNumber; value != nil {
			if *value <= 2 {
				tags[capturePhotographyTagRoot+"/拍摄参数/光圈/大光圈虚化"] = struct{}{}
			} else if *value >= 11 {
				tags[capturePhotographyTagRoot+"/拍摄参数/光圈/小光圈全景深"] = struct{}{}
			}
		}
		if value := metadata.ISOSensitivity; value != nil {
			if *value >= 3200 {
				tags[capturePhotographyTagRoot+"/拍摄参数/感光度/高感夜拍"] = struct{}{}
			} else if *value <= 200 {
				tags[capturePhotographyTagRoot+"/拍摄参数/感光度/低感画质"] = struct{}{}
			}
		}
	}
	if disclosed["place"] && disclosed["time"] &&
		metadata.CapturedAt != nil && metadata.GPSLatitude != nil && metadata.GPSLongitude != nil {
		elevation := captureSolarElevationDegrees(
			metadata.CapturedAt.UTC(), *metadata.GPSLatitude, *metadata.GPSLongitude,
		)
		window := "正午强光"
		switch {
		case elevation < -6:
			window = "夜间无日光"
		case elevation < -4:
			window = "蓝调时刻"
		case elevation < 6:
			window = "金色时刻"
		case elevation <= 60:
			window = "白天漫射光"
		}
		tags[capturePhotographyTagRoot+"/光线条件/"+window] = struct{}{}
	}
	result := make([]string, 0, len(tags))
	for tag := range tags {
		result = append(result, tag)
	}
	sort.Strings(result)
	return result
}

func captureFocalRange(value *float64) string {
	if value == nil || *value <= 0 {
		return ""
	}
	switch {
	case *value < 20:
		return "超广角"
	case *value < 35:
		return "广角"
	case *value < 70:
		return "标准"
	case *value < 135:
		return "中长焦"
	case *value < 300:
		return "长焦"
	default:
		return "超长焦"
	}
}

func captureBodyType(metadata mediamodel.CaptureMetadata) string {
	combined := strings.ToUpper(strings.TrimSpace(metadata.CameraMake + " " + metadata.CameraModel))
	if combined == "" {
		return ""
	}
	cases := []struct {
		label   string
		needles []string
	}{
		{"无人机航拍", []string{"DJI", "AUTEL", "MAVIC", "PHANTOM", "AIR 2S"}},
		{"运动相机", []string{"GOPRO", "HERO", "INSTA360", "OSMO ACTION", "ACTION 4"}},
		{"手机拍摄", []string{"APPLE", "IPHONE", "XIAOMI", "REDMI", "HUAWEI", "HONOR", "OPPO", "VIVO", "ONEPLUS", "SAMSUNG", "GOOGLE", "PIXEL", "MEIZU", "REALME"}},
		{"中画幅", []string{"GFX", "HASSELBLAD", "X1D", "PHASE ONE", "IQ4", "645Z"}},
		{"单反相机", []string{"EOS 5D", "EOS 6D", "EOS 1D", "EOS 90D", "EOS 80D", "D850", "D780", "D750", "D7500", "D5600", "K-1", "K-3", "SLT-"}},
		{"胶片扫描", []string{"EPSON", "PLUSTEK", "COOLSCAN", "NORITSU", "FRONTIER SP"}},
		{"半画幅微单", []string{"ILCE-6", "ILCE-5", "ZV-E10", "X-T", "X-S", "X-E", "X-PRO", "X100", "EOS R7", "EOS R10", "EOS R50", "EOS M", "Z 50", "Z 30", "Z FC", "E-M", "OM-", "DC-G", "DC-GH"}},
		{"全画幅微单", []string{"ILCE-7", "ILCE-1", "ILCE-9", "EOS R", "Z 6", "Z 7", "Z 8", "Z 9", "DC-S", "SIGMA FP", "L-MOUNT"}},
	}
	for _, candidate := range cases {
		if captureContainsAny(combined, candidate.needles) {
			return candidate.label
		}
	}
	return ""
}

func captureLensTypes(value string) []string {
	upper := strings.ToUpper(strings.TrimSpace(value))
	if upper == "" {
		return nil
	}
	result := make([]string, 0, 4)
	if captureContainsAny(upper, []string{"MACRO", "微距", "MP-E"}) {
		result = append(result, "微距镜头")
	}
	if captureContainsAny(upper, []string{"FISHEYE", "鱼眼"}) {
		result = append(result, "鱼眼镜头")
	}
	if captureContainsAny(upper, []string{"TS-E", "PC-E", "TILT", "移轴"}) {
		result = append(result, "移轴镜头")
	}
	if captureLensZoomPattern.MatchString(upper) {
		result = append(result, "变焦镜头")
	} else if captureLensPrimePattern.MatchString(upper) {
		result = append(result, "定焦镜头")
	}
	return result
}

func captureContainsAny(value string, needles []string) bool {
	for _, needle := range needles {
		if strings.Contains(value, needle) {
			return true
		}
	}
	return false
}

// NOAA low-precision solar position algorithm, kept byte-for-byte equivalent
// in thresholds to the App implementation used for local preview.
func captureSolarElevationDegrees(capturedAt time.Time, latitude, longitude float64) float64 {
	utc := capturedAt.UTC()
	julianDay := captureJulianDay(utc)
	t := (julianDay - 2451545.0) / 36525.0
	geomMeanLongSun := captureWrapPositive(280.46646+t*(36000.76983+t*0.0003032), 360)
	geomMeanAnomalySun := 357.52911 + t*(35999.05029-0.0001537*t)
	eccentricity := 0.016708634 - t*(0.000042037+0.0000001267*t)
	anomalyRad := captureRadians(geomMeanAnomalySun)
	equationOfCenter := math.Sin(anomalyRad)*(1.914602-t*(0.004817+0.000014*t)) +
		math.Sin(2*anomalyRad)*(0.019993-0.000101*t) + math.Sin(3*anomalyRad)*0.000289
	trueLongitude := geomMeanLongSun + equationOfCenter
	apparentLongitude := trueLongitude - 0.00569 - 0.00478*math.Sin(captureRadians(125.04-1934.136*t))
	meanObliquity := 23 + (26+(21.448-t*(46.815+t*(0.00059-t*0.001813)))/60)/60
	obliquity := meanObliquity + 0.00256*math.Cos(captureRadians(125.04-1934.136*t))
	declination := captureDegrees(math.Asin(math.Sin(captureRadians(obliquity)) * math.Sin(captureRadians(apparentLongitude))))
	varY := math.Tan(captureRadians(obliquity/2)) * math.Tan(captureRadians(obliquity/2))
	equationOfTime := 4 * captureDegrees(
		varY*math.Sin(2*captureRadians(geomMeanLongSun))-
			2*eccentricity*math.Sin(anomalyRad)+
			4*eccentricity*varY*math.Sin(anomalyRad)*math.Cos(2*captureRadians(geomMeanLongSun))-
			0.5*varY*varY*math.Sin(4*captureRadians(geomMeanLongSun))-
			1.25*eccentricity*eccentricity*math.Sin(2*anomalyRad),
	)
	minutesUTC := float64(utc.Hour()*60+utc.Minute()) + float64(utc.Second())/60 + float64(utc.Nanosecond())/float64(time.Millisecond)/60000
	trueSolarTime := captureWrapPositive(minutesUTC+equationOfTime+4*longitude, 1440)
	hourAngle := trueSolarTime/4 - 180
	latRad := captureRadians(latitude)
	decRad := captureRadians(declination)
	cosZenith := math.Sin(latRad)*math.Sin(decRad) + math.Cos(latRad)*math.Cos(decRad)*math.Cos(captureRadians(hourAngle))
	cosZenith = math.Max(-1, math.Min(1, cosZenith))
	return 90 - captureDegrees(math.Acos(cosZenith))
}

func captureJulianDay(utc time.Time) float64 {
	year, month := utc.Year(), int(utc.Month())
	if month <= 2 {
		year--
		month += 12
	}
	a := int(math.Floor(float64(year) / 100))
	b := 2 - a + int(math.Floor(float64(a)/4))
	dayFraction := (float64(utc.Hour()) + float64(utc.Minute())/60 + float64(utc.Second())/3600) / 24
	return math.Floor(365.25*float64(year+4716)) + math.Floor(30.6001*float64(month+1)) +
		float64(utc.Day()) + dayFraction + float64(b) - 1524.5
}

func captureRadians(value float64) float64 { return value * math.Pi / 180 }
func captureDegrees(value float64) float64 { return value * 180 / math.Pi }
func captureWrapPositive(value, period float64) float64 {
	result := math.Mod(value, period)
	if result < 0 {
		return result + period
	}
	return result
}
