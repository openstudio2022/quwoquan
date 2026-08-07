package runtimeconfig

import (
	"testing"
	"time"
)

// RuntimeConfigProvider 有两个实现（env 与 map），代码几乎逐行重复。
// 重复实现最容易出现的失效不是「某个实现坏了」，而是「两个实现悄悄分叉」——
// 于是 map 驱动的 local_contract 测试通过、真实环境按 env 读取却是另一套语义。
//
// 因此这里所有用例都以同一张表跑过两个实现：map 用例直接注入，env 用例通过
// t.Setenv 注入同样的原始字符串。任何一侧改了 trim / 边界 / 解析容错，
// 都会在这里立刻暴露成不一致。
//
// 被钉住的边界语义：
//   - 空值与全空白等价于「未配置」（false），不是「配置成了空串」（true）。
//     否则缺省会被当成显式空配置，覆盖掉下游的真实默认值。
//   - 无法解析的整数返回 false，而不是静默取 0。
//   - GetDurationMs 拒绝 <= 0：`0` 与负数是误配置，不得被读成「无超时」。
//   - GetIntList 对任一非法分片整体失败，不做部分接受；全空分片视为未配置。

// providerUnderTest 把「同一份原始配置」绑定到两个实现上。
type providerUnderTest struct {
	name string
	// build 以给定的 key/value 原始字符串装配一个 provider。
	build func(t *testing.T, key, rawValue string) RuntimeConfigProvider
}

func providersUnderTest() []providerUnderTest {
	return []providerUnderTest{
		{
			name: "EnvRuntimeConfigProvider",
			build: func(t *testing.T, key, rawValue string) RuntimeConfigProvider {
				t.Helper()
				t.Setenv(key, rawValue)
				return EnvRuntimeConfigProvider{}
			},
		},
		{
			name: "MapRuntimeConfigProvider",
			build: func(t *testing.T, key, rawValue string) RuntimeConfigProvider {
				t.Helper()
				return MapRuntimeConfigProvider{Values: map[string]string{key: rawValue}}
			},
		},
	}
}

const testKey = "QWQ_RUNTIME_CONFIG_CONTRACT_KEY"

func TestGetStringTreatsBlankAsUnconfigured(t *testing.T) {
	cases := []struct {
		name      string
		raw       string
		wantValue string
		wantOK    bool
	}{
		{name: "plain value", raw: "gamma", wantValue: "gamma", wantOK: true},
		{name: "surrounding whitespace is trimmed", raw: "  gamma\t", wantValue: "gamma", wantOK: true},
		{name: "inner whitespace is preserved", raw: "  a b  ", wantValue: "a b", wantOK: true},
		{name: "empty is unconfigured", raw: "", wantOK: false},
		{name: "whitespace only is unconfigured", raw: "   \t\n ", wantOK: false},
	}

	for _, provider := range providersUnderTest() {
		for _, tc := range cases {
			t.Run(provider.name+"/"+tc.name, func(t *testing.T) {
				got, ok := provider.build(t, testKey, tc.raw).GetString(testKey)
				if ok != tc.wantOK {
					t.Fatalf("GetString(%q) ok = %v, want %v", tc.raw, ok, tc.wantOK)
				}
				if ok && got != tc.wantValue {
					t.Fatalf("GetString(%q) = %q, want %q", tc.raw, got, tc.wantValue)
				}
				if !ok && got != "" {
					t.Fatalf("GetString(%q) returned %q alongside ok=false; an absent key must yield the zero value", tc.raw, got)
				}
			})
		}
	}
}

func TestGetIntRejectsUnparseableValuesInsteadOfDefaultingToZero(t *testing.T) {
	cases := []struct {
		name   string
		raw    string
		want   int
		wantOK bool
	}{
		{name: "positive", raw: "42", want: 42, wantOK: true},
		{name: "negative", raw: "-7", want: -7, wantOK: true},
		{name: "explicit zero is a valid int", raw: "0", want: 0, wantOK: true},
		{name: "padded", raw: " 42 ", want: 42, wantOK: true},
		{name: "not a number", raw: "abc", wantOK: false},
		{name: "float is not an int", raw: "1.5", wantOK: false},
		{name: "trailing unit is rejected", raw: "500ms", wantOK: false},
		{name: "unconfigured", raw: "", wantOK: false},
	}

	for _, provider := range providersUnderTest() {
		for _, tc := range cases {
			t.Run(provider.name+"/"+tc.name, func(t *testing.T) {
				got, ok := provider.build(t, testKey, tc.raw).GetInt(testKey)
				if ok != tc.wantOK {
					t.Fatalf("GetInt(%q) ok = %v, want %v", tc.raw, ok, tc.wantOK)
				}
				if ok && got != tc.want {
					t.Fatalf("GetInt(%q) = %d, want %d", tc.raw, got, tc.want)
				}
			})
		}
	}
}

func TestGetDurationMsRejectsNonPositiveBudgets(t *testing.T) {
	cases := []struct {
		name   string
		raw    string
		want   time.Duration
		wantOK bool
	}{
		{name: "positive milliseconds", raw: "250", want: 250 * time.Millisecond, wantOK: true},
		{name: "one millisecond", raw: "1", want: time.Millisecond, wantOK: true},
		{name: "zero is a misconfiguration, not unlimited", raw: "0", wantOK: false},
		{name: "negative is a misconfiguration", raw: "-1", wantOK: false},
		{name: "unparseable", raw: "fast", wantOK: false},
		{name: "unconfigured", raw: "", wantOK: false},
	}

	for _, provider := range providersUnderTest() {
		for _, tc := range cases {
			t.Run(provider.name+"/"+tc.name, func(t *testing.T) {
				got, ok := provider.build(t, testKey, tc.raw).GetDurationMs(testKey)
				if ok != tc.wantOK {
					t.Fatalf("GetDurationMs(%q) ok = %v, want %v", tc.raw, ok, tc.wantOK)
				}
				if ok && got != tc.want {
					t.Fatalf("GetDurationMs(%q) = %v, want %v", tc.raw, got, tc.want)
				}
				if !ok && got != 0 {
					t.Fatalf("GetDurationMs(%q) returned %v alongside ok=false", tc.raw, got)
				}
			})
		}
	}
}

func TestGetIntListFailsWholeValueOnAnyIllegalPart(t *testing.T) {
	cases := []struct {
		name   string
		raw    string
		want   []int
		wantOK bool
	}{
		{name: "single", raw: "1", want: []int{1}, wantOK: true},
		{name: "multiple", raw: "1,2,3", want: []int{1, 2, 3}, wantOK: true},
		{name: "padded parts are trimmed", raw: " 1 , 2 ,3 ", want: []int{1, 2, 3}, wantOK: true},
		{name: "blank parts are skipped", raw: "1,,2,", want: []int{1, 2}, wantOK: true},
		{name: "order is preserved", raw: "3,1,2", want: []int{3, 1, 2}, wantOK: true},
		{name: "duplicates are preserved", raw: "1,1", want: []int{1, 1}, wantOK: true},
		{name: "negatives are allowed", raw: "-1,2", want: []int{-1, 2}, wantOK: true},
		{name: "one illegal part rejects the whole list", raw: "1,x,3", wantOK: false},
		{name: "only separators is unconfigured", raw: ",,,", wantOK: false},
		{name: "unconfigured", raw: "", wantOK: false},
	}

	for _, provider := range providersUnderTest() {
		for _, tc := range cases {
			t.Run(provider.name+"/"+tc.name, func(t *testing.T) {
				got, ok := provider.build(t, testKey, tc.raw).GetIntList(testKey)
				if ok != tc.wantOK {
					t.Fatalf("GetIntList(%q) ok = %v, want %v", tc.raw, ok, tc.wantOK)
				}
				if !ok {
					if got != nil {
						t.Fatalf("GetIntList(%q) returned %v alongside ok=false; callers must not see a partial list", tc.raw, got)
					}
					return
				}
				if len(got) != len(tc.want) {
					t.Fatalf("GetIntList(%q) = %v, want %v", tc.raw, got, tc.want)
				}
				for i := range tc.want {
					if got[i] != tc.want[i] {
						t.Fatalf("GetIntList(%q) = %v, want %v", tc.raw, got, tc.want)
					}
				}
			})
		}
	}
}

func TestMissingKeyIsUnconfiguredAcrossEveryAccessor(t *testing.T) {
	const absentKey = "QWQ_RUNTIME_CONFIG_ABSENT_KEY"

	// map 侧还要覆盖 nil map：未装配的 provider 不得 panic，必须表现为「全部未配置」。
	providers := map[string]RuntimeConfigProvider{
		"EnvRuntimeConfigProvider":          EnvRuntimeConfigProvider{},
		"MapRuntimeConfigProvider/nil":      MapRuntimeConfigProvider{},
		"MapRuntimeConfigProvider/empty":    MapRuntimeConfigProvider{Values: map[string]string{}},
		"MapRuntimeConfigProvider/otherKey": MapRuntimeConfigProvider{Values: map[string]string{"OTHER": "1"}},
	}

	for name, provider := range providers {
		t.Run(name, func(t *testing.T) {
			if _, ok := provider.GetString(absentKey); ok {
				t.Fatal("GetString reported an absent key as configured")
			}
			if _, ok := provider.GetInt(absentKey); ok {
				t.Fatal("GetInt reported an absent key as configured")
			}
			if _, ok := provider.GetDurationMs(absentKey); ok {
				t.Fatal("GetDurationMs reported an absent key as configured")
			}
			if _, ok := provider.GetIntList(absentKey); ok {
				t.Fatal("GetIntList reported an absent key as configured")
			}
		})
	}
}

func TestMapProviderIsolatesKeys(t *testing.T) {
	provider := MapRuntimeConfigProvider{Values: map[string]string{
		"A": "1",
		"B": "abc",
	}}

	if got, ok := provider.GetInt("A"); !ok || got != 1 {
		t.Fatalf(`GetInt("A") = (%d, %v), want (1, true)`, got, ok)
	}
	if _, ok := provider.GetInt("B"); ok {
		t.Fatal(`GetInt("B") must fail without affecting sibling keys`)
	}
	if got, ok := provider.GetString("B"); !ok || got != "abc" {
		t.Fatalf(`GetString("B") = (%q, %v), want ("abc", true)`, got, ok)
	}
}
