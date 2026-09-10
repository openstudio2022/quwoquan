"""文章的百科事实参考原文。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/toutiao.py", "producer_toutiao")
fetch = client.fetch
parse = client.parse
