# data-admin-region

补全行政区标签节点（省/市/区县），幂等执行。

## 执行

```bash
# 补全所有已定义省份
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py

# 补全指定省份
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py --province 四川省

# 补全指定省份下的指定城市
python3 quwoquan_data/scripts/bootstrap/taxonomy/bootstrap_admin_regions.py --province 四川省 --city 成都市
```

## 扩展新省份

在 `bootstrap_admin_regions.py` 中添加省份数据字典，格式：

```python
GUANGDONG = {
    "广州市": ("Guangzhou", "广东省省会", {
        "越秀区": ("Yuexiu", "广州核心区"),
        ...
    }),
    ...
}
```

然后在 `main()` 的 `provinces` 字典中注册。

## 输出位置

`quwoquan_data/publish/tags/地理/行政区/{省}/{市}/{区县}/`

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-admin-region` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
