package iplocation_test

import (
	. "quwoquan_service/services/content-service/internal/content/comment/infrastructure/iplocation"
	"testing"
)

func TestDisplayLocationUsesProvinceForChinaAndCountryForOverseas(
	t *testing.T,
) {
	t.Parallel()

	tests := []struct {
		name   string
		region string
		want   string
	}{
		{
			name:   "domestic province",
			region: "中国|浙江省|杭州市|电信|CN",
			want:   "浙江",
		},
		{
			name:   "municipality",
			region: "中国|北京市|北京市|联通|CN",
			want:   "北京",
		},
		{
			name:   "autonomous region",
			region: "中国|新疆维吾尔自治区|乌鲁木齐市|移动|CN",
			want:   "新疆",
		},
		{
			name:   "overseas country",
			region: "United States|California|Los Angeles|0|US",
			want:   "United States",
		},
		{
			name:   "missing domestic province",
			region: "中国|0|0|0|CN",
			want:   "",
		},
		{
			name:   "invalid record",
			region: "invalid",
			want:   "",
		},
	}

	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			if got := DisplayLocation(test.region); got != test.want {
				t.Fatalf("displayLocation(%q) = %q, want %q", test.region, got, test.want)
			}
		})
	}
}

func TestIP2RegionResolverRejectsInvalidOrPrivateIPWithoutDatabaseLookup(
	t *testing.T,
) {
	t.Parallel()

	resolver := &IP2RegionResolver{}
	for _, ip := range []string{"", "not-an-ip", "127.0.0.1", "10.0.0.1", "::1"} {
		if got := resolver.Resolve(ip); got != "" {
			t.Fatalf("Resolve(%q) = %q, want empty", ip, got)
		}
	}
}
