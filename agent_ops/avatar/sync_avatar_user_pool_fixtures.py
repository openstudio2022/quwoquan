#!/usr/bin/env python3
"""兼容旧入口：统一转发到真实图片共享池流水线。"""

from __future__ import annotations

from shared_pool_real_asset_pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())
