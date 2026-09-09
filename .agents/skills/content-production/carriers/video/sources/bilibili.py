"""Bilibili 显式有界单条/UP 元数据；412/挑战页只报告，不绕过。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/ytdlp.py", "producer_ytdlp")


def fetch(request, transport):
    return client.fetch(request, transport, {"bilibili.com", "www.bilibili.com", "space.bilibili.com", "b23.tv"})


def parse(body, request):
    return client.parse(body, request, "bilibili")
