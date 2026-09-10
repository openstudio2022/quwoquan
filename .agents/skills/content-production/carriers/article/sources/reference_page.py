"""公开游记、公告或新闻的事实底稿；来源资格与相关性由 AI 决定。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/webpage.py", "producer_webpage")
fetch = client.fetch
parse = client.parse
