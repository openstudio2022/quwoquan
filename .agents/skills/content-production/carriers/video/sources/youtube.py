"""YouTube 显式有界单条/频道元数据；CC 与实体选择由宿主核查。"""
import inputs

client = inputs.module(inputs.SKILL / "scripts/clients/ytdlp.py", "producer_ytdlp")


def fetch(request, transport):
    return client.fetch(request, transport, {"youtube.com", "www.youtube.com", "youtu.be"})


def parse(body, request):
    return client.parse(body, request, "youtube")
