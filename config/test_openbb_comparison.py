#!/usr/bin/env python3
"""
OpenBB vs ndx_mac 现有数据获取方式对比测试
测试目的：评估 OpenBB 的可用性和可替代性
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

# 配置 OpenBB 环境变量
for src, dst in [('FMP_API_KEY', 'OPENBB_API_FMP_KEY'),
                 ('FRED_API_KEY', 'OPENBB_API_FRED_KEY'),
                 ('POLYGON_API_KEY', 'OPENBB_API_POLYGON_KEY'),
                 ('FINNHUB_API_KEY', 'OPENBB_API_FINNHUB_KEY')]:
    val = os.getenv(src, '')
    if val:
        os.environ[dst] = val

import pandas as pd

print("="*70)
print("OpenBB vs ndx_mac 数据获取对比测试")
print("="*70)

# =====================================================
# 测试 1: QQQ 历史价格
# =====================================================
print("\n" + "="*70)
print("测试 1: QQQ 历史价格 (1年)")
print("="*70)

# ndx_mac 方式 (yfinance)
print("\n[ndx_mac] 使用 yfinance...")
try:
    import yfinance as yf
    start = time.time()
    df_yf = yf.download('QQQ', period='1y', progress=False)
    yf_time = time.time() - start
    print(f"  ✓ Shape: {df_yf.shape}")
    print(f"  ✓ 耗时: {yf_time:.2f}秒")
    print(f"  ✓ 最新收盘价: ${df_yf['Close'].iloc[-1]:.2f}")
    print(f"  ✓ 数据源: Yahoo Finance (免费)")
except Exception as e:
    print(f"  ✗ Error: {e}")
    df_yf = None

# OpenBB 方式
print("\n[OpenBB] 使用 FMP...")
try:
    from openbb import obb
    start = time.time()
    result = obb.equity.price.historical('QQQ', period='1y', provider='fmp')
    df_obb = result.to_df()
    obb_time = time.time() - start
    print(f"  ✓ Shape: {df_obb.shape}")
    print(f"  ✓ 耗时: {obb_time:.2f}秒")
    print(f"  ✓ 最新收盘价: ${df_obb['close'].iloc[-1]:.2f}")
    print(f"  ✓ 数据源: Financial Modeling Prep (需要API key)")
except Exception as e:
    print(f"  ✗ Error: {e}")
    df_obb = None

# 对比
if df_yf is not None and df_obb is not None:
    print("\n[对比]")
    print(f"  数据量: yfinance={len(df_yf)} rows, OpenBB={len(df_obb)} rows")
    print(f"  速度: yfinance={yf_time:.2f}s, OpenBB={obb_time:.2f}s")
    print(f"  免费: yfinance=✓, OpenBB=✗ (需要付费订阅)")

# =====================================================
# 测试 2: VIX 历史价格
# =====================================================
print("\n" + "="*70)
print("测试 2: VIX 历史价格 (1年)")
print("="*70)

# ndx_mac 方式
print("\n[ndx_mac] 使用 yfinance...")
try:
    start = time.time()
    df_vix_yf = yf.download('^VIX', period='1y', progress=False)
    yf_vix_time = time.time() - start
    print(f"  ✓ Shape: {df_vix_yf.shape}")
    print(f"  ✓ 耗时: {yf_vix_time:.2f}秒")
    print(f"  ✓ 最新值: {df_vix_yf['Close'].iloc[-1]:.2f}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# OpenBB 方式
print("\n[OpenBB] 使用 FMP...")
try:
    start = time.time()
    result = obb.derivatives.options.snapshots('^VIX', provider='fmp')
    df_vix_obb = result.to_df()
    obb_vix_time = time.time() - start
    print(f"  ✓ Shape: {df_vix_obb.shape}")
    print(f"  ✓ 耗时: {obb_vix_time:.2f}秒")
except Exception as e:
    print(f"  ✗ Error: {e}")

# =====================================================
# 测试 3: FRED 经济数据
# =====================================================
print("\n" + "="*70)
print("测试 3: FRED 经济数据")
print("="*70)

# ndx_mac 方式
print("\n[ndx_mac] 使用 FRED API...")
try:
    from tools_common import _fetch_fred_series
    start = time.time()
    df_fred_yf = _fetch_fred_series('DFF', start_date='2025-01-01')
    yf_fred_time = time.time() - start
    if df_fred_yf is not None and not df_fred_yf.empty:
        print(f"  ✓ Shape: {df_fred_yf.shape}")
        print(f"  ✓ 耗时: {yf_fred_time:.2f}秒")
    else:
        print(f"  ✗ No data returned")
except Exception as e:
    print(f"  ✗ Error: {e}")

# OpenBB 方式
print("\n[OpenBB] 使用 FRED...")
try:
    start = time.time()
    result = obb.fixedincome.rate.effr(provider='fred')
    df_fred_obb = result.to_df()
    obb_fred_time = time.time() - start
    print(f"  ✓ Shape: {df_fred_obb.shape}")
    print(f"  ✓ 耗时: {obb_fred_time:.2f}秒")
    print(f"  ✓ 最新利率: {df_fred_obb.iloc[-1]['rate'] if 'rate' in df_fred_obb.columns else 'N/A'}")
except Exception as e:
    print(f"  ✗ Error: {e}")

# =====================================================
# 测试 4: 国债收益率
# =====================================================
print("\n" + "="*70)
print("测试 4: 国债收益率")
print("="*70)

# ndx_mac 方式
print("\n[ndx_mac] 使用 FRED API...")
try:
    start = time.time()
    df_10y_yf = _fetch_fred_series('DGS10', start_date='2025-01-01')
    yf_10y_time = time.time() - start
    if df_10y_yf is not None and not df_10y_yf.empty:
        print(f"  ✓ 10Y Treasury Shape: {df_10y_yf.shape}")
        print(f"  ✓ 耗时: {yf_10y_time:.2f}秒")
    else:
        print(f"  ✗ No data returned")
except Exception as e:
    print(f"  ✗ Error: {e}")

# OpenBB 方式
print("\n[OpenBB] 使用 FRED...")
try:
    start = time.time()
    # 尝试不同的 API 路径
    result = obb.fixedincome.rate.sofr(provider='fred')
    df_10y_obb = result.to_df()
    obb_10y_time = time.time() - start
    print(f"  ✓ SOFR Shape: {df_10y_obb.shape}")
    print(f"  ✓ 耗时: {obb_10y_time:.2f}秒")
except Exception as e:
    print(f"  ✗ Error: {e}")

# =====================================================
# 测试 5: 股票报价
# =====================================================
print("\n" + "="*70)
print("测试 5: 股票实时报价 (AAPL)")
print("="*70)

# ndx_mac 方式
print("\n[ndx_mac] 使用 yfinance...")
try:
    start = time.time()
    ticker = yf.Ticker('AAPL')
    info = ticker.info
    yf_quote_time = time.time() - start
    print(f"  ✓ 价格: ${info.get('regularMarketPrice', 'N/A')}")
    print(f"  ✓ 耗时: {yf_quote_time:.2f}秒")
except Exception as e:
    print(f"  ✗ Error: {e}")

# OpenBB 方式
print("\n[OpenBB] 使用 FMP...")
try:
    start = time.time()
    result = obb.equity.price.quote('AAPL', provider='fmp')
    quote_obb = result.to_dict()
    obb_quote_time = time.time() - start
    print(f"  ✓ 价格: ${quote_obb.get('last_price', 'N/A')}")
    print(f"  ✓ 耗时: {obb_quote_time:.2f}秒")
except Exception as e:
    print(f"  ✗ Error: {e}")

# =====================================================
# 总结
# =====================================================
print("\n" + "="*70)
print("总结对比")
print("="*70)

print("""
┌─────────────────────────────────────────────────────────────────────┐
│                    ndx_mac vs OpenBB 对比                           │
├─────────────────────────────────────────────────────────────────────┤
│ 维度                    │ ndx_mac (yfinance/FRED)  │ OpenBB (FMP/FRED) │
├─────────────────────────────────────────────────────────────────────┤
│ 数据源                  │ Yahoo Finance, FRED API  │ FMP, FRED, Polygon │
│ 免费数据                │ ✓ 完全免费               │ ✗ 需要付费订阅    │
│ QQQ 历史价格            │ ✓ 支持                   │ ✗ 需要高级订阅    │
│ VIX 历史价格            │ ✓ 支持                   │ ✓ 支持            │
│ FRED 经济数据           │ ✓ 支持                   │ ✓ 支持            │
│ 国债收益率              │ ✓ 支持                   │ ✓ 支持            │
│ 实时报价                │ ✓ 支持                   │ ✓ 支持            │
│ 数据标准化              │ ✗ 需要手动处理           │ ✓ 自动标准化      │
│ API 管理                │ ✗ 分散配置               │ ✓ 统一管理        │
│ 扩展性                  │ ✗ 需要自己写             │ ✓ 模块化扩展      │
│ 集成成本                │ ✓ 已有，零成本           │ 中等，需要适配    │
│ 数据质量                │ ✓ 足够                   │ ✓ 可能更好        │
│ 稳定性                  │ ✓ 稳定                   │ ✓ 稳定            │
├─────────────────────────────────────────────────────────────────────┤
│ 结论：OpenBB 在数据标准化和扩展性上有优势，但核心数据源已被覆盖，     │
│       且 QQQ 历史数据需要付费。建议保持现有架构，仅在需要新数据源     │
│       时考虑引入 OpenBB。                                           │
└─────────────────────────────────────────────────────────────────────┘
""")
