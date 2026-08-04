package providerbinding

// Adapter identity constants are discovered by external_provider_governance.
const (
	ModelAdapterXiaomiMimo      = "ext.llm.xiaomi_mimo"
	ModelAdapterProtocolFixture = "ext.llm.protocol_fixture"

	SearchAdapterDuckDuckGoHTML  = "ext.search.duckduckgo_html"
	SearchAdapterProtocolFixture = "ext.search.protocol_fixture"

	WeatherAdapterOpenMeteo       = "ext.weather.open_meteo"
	WeatherAdapterProtocolFixture = "ext.weather.protocol_fixture"

	FinanceAdapterYahooChart      = "ext.finance.yahoo_chart"
	FinanceAdapterProtocolFixture = "ext.finance.protocol_fixture"
)

// ModelAdapterIDs 是 assistant.model.generation 允许绑定的 adapter 全集。所有条目都必须
// 说 OpenAI 兼容的 completion 协议，因此新增供应商只需在此登记一行并补齐三层
// provider conformance，无需改动 composition root 或 adapter 实现。
func ModelAdapterIDs() []string {
	return []string{
		ModelAdapterXiaomiMimo,
		ModelAdapterProtocolFixture,
	}
}
