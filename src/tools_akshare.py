# tools_akshare.py
# -*- coding: utf-8 -*-
"""
NDX Agent · AKShare数据工具包 - 备用数据源
用途：为关键指标提供AKShare作为备用数据源，当yfinance失败时降级使用

支持的指标：
1. VIX恐慌指数
2. 铜金比率（期货价格）
3. QQQ Put/Call比率（期权市场情绪）

架构说明：
- 本模块作为tools.py的补充，不替代主数据源
- 遵循"弹性回退"原则：优先yfinance，失败时降级到AKShare
- 保持与tools.py相同的返回格式，确保向后兼容
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# 尝试导入AKShare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
    logging.info("✅ AKShare库已成功加载")
except ImportError:
    AKSHARE_AVAILABLE = False
    logging.warning("⚠ AKShare未安装，备用数据源不可用。安装命令: pip install akshare")

# =====================================================
# 第二层：市场风险偏好 - AKShare备用实现
# =====================================================

def get_vix_akshare(end_date: Optional[str] = None) -> Dict[str, Any]:
    """
    从AKShare获取中国市场波动率指数（备用数据源）
    
    数据源：AKShare的中国市场QVIX指数（如50ETF期权波动率指数）
    用途：当yfinance的^VIX获取失败时，提供中国市场的波动率作为全球市场情绪的参考
    
    注意：
    - AKShare不直接提供美股VIX数据
    - 使用中国50ETF期权波动率指数作为全球市场情绪的代理指标
    - 两者趋势具有一定相关性，但绝对值不可直接比较
    
    参数:
        end_date: 指定日期（YYYY-MM-DD），None表示最新数据
    
    返回:
        标准化的字典格式，与tools.py中的get_vix()保持一致
    """
    if not AKSHARE_AVAILABLE:
        return {
            "name": "VIX (AKShare)",
            "value": None,
            "notes": "AKShare库未安装，无法使用备用数据源"
        }
    
    try:
        # 使用50ETF期权波动率指数（中国市场的VIX等价物）
        df = ak.index_option_50etf_qvix()
        
        if df is None or df.empty:
            raise ValueError("AKShare返回空数据")
        
        # 数据清洗：确保日期列格式正确
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 如果指定了end_date，筛选数据
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
            df = df[df['date'] <= effective_date]
        
        if df.empty:
            raise ValueError(f"在指定日期 {end_date} 之前无可用数据")
        
        # 获取最新值（QVIX列）
        latest_row = df.iloc[-1]
        qvix_value = float(latest_row['qvix'])
        qvix_date = latest_row['date'].strftime("%Y-%m-%d")
        
        return {
            "name": "China 50ETF QVIX (AKShare Fallback)",
            "series_id": "QVIX_50ETF_AKSHARE",
            "value": {
                "level": round(qvix_value, 2),
                "date": qvix_date
            },
            "unit": "index",
            "source_name": "AKShare (中国50ETF期权波动率，备用源)",
            "notes": "中国市场波动率指数，作为全球市场情绪的参考指标（yfinance VIX备用源）"
        }
        
    except Exception as e:
        logging.error(f"AKShare QVIX获取失败: {str(e)[:100]}")
        return {
            "name": "VIX (AKShare)",
            "value": None,
            "notes": f"AKShare不支持美股VIX，中国市场QVIX获取也失败: {str(e)[:100]}"
        }


def get_copper_gold_ratio_akshare(end_date: Optional[str] = None) -> Dict[str, Any]:
    """
    从AKShare获取铜金比率（备用数据源）
    
    数据源：AKShare的期货主力合约数据
    - 铜: futures_main_sina(symbol="CU0") - 上期所铜主力
    - 黄金: futures_main_sina(symbol="AU0") - 上期所金主力
    
    注意：
    - AKShare提供的是中国期货市场数据（上海期货交易所）
    - 与yfinance的美国期货（HG=F, GC=F）存在价格差异
    - 但比率趋势具有全球一致性，可作为备用指标
    - 当前AKShare的期货接口存在稳定性问题，此函数为实验性质
    
    参数:
        end_date: 指定日期（YYYY-MM-DD），None表示最新数据
    
    返回:
        标准化的字典格式，与tools.py中的get_copper_gold_ratio()保持一致
    """
    if not AKSHARE_AVAILABLE:
        return {
            "name": "Copper/Gold Ratio (AKShare)",
            "value": None,
            "notes": "AKShare库未安装，无法使用备用数据源"
        }
    
    try:
        # 获取铜期货主力合约数据（上期所）
        # 注意：AKShare 1.17.x版本的API已更新，不再需要market参数
        copper_df = ak.futures_main_sina(symbol="CU0")
        
        # 获取黄金期货主力合约数据（上期所）
        gold_df = ak.futures_main_sina(symbol="AU0")
        
        if copper_df is None or copper_df.empty or gold_df is None or gold_df.empty:
            raise ValueError("AKShare期货数据返回空")
        
        # 数据清洗
        copper_df['date'] = pd.to_datetime(copper_df['date'])
        gold_df['date'] = pd.to_datetime(gold_df['date'])
        
        # 如果指定了end_date，筛选数据
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
            copper_df = copper_df[copper_df['date'] <= effective_date]
            gold_df = gold_df[gold_df['date'] <= effective_date]
        
        if copper_df.empty or gold_df.empty:
            raise ValueError(f"在指定日期 {end_date} 之前无可用数据")
        
        # 获取最新价格
        copper_price = float(copper_df.iloc[-1]['close'])
        gold_price = float(gold_df.iloc[-1]['close'])
        copper_date = copper_df.iloc[-1]['date'].strftime("%Y-%m-%d")
        gold_date = gold_df.iloc[-1]['date'].strftime("%Y-%m-%d")
        
        # 计算比率
        ratio = copper_price / gold_price
        
        return {
            "name": "Copper/Gold Ratio (AKShare Fallback)",
            "series_id": "COPPER_GOLD_RATIO_AKSHARE",
            "value": {
                "level": round(ratio, 4),
                "date": copper_date,
                "components": {
                    "Copper (SHFE CU0)": f"{copper_price:.2f} CNY/ton",
                    "Gold (SHFE AU0)": f"{gold_price:.2f} CNY/gram"
                }
            },
            "unit": "ratio",
            "source_name": "AKShare (上期所期货，备用源)",
            "notes": "铜金比率，从AKShare获取（中国期货市场数据，yfinance备用源）"
        }
        
    except Exception as e:
        logging.error(f"AKShare铜金比获取失败: {str(e)[:100]}")
        return {
            "name": "Copper/Gold Ratio (AKShare)",
            "value": None,
            "notes": f"AKShare期货接口不稳定，获取失败: {str(e)[:100]}"
        }


def get_qqq_put_call_akshare(end_date: Optional[str] = None) -> Dict[str, Any]:
    """
    从AKShare获取QQQ Put/Call比率（备用数据源）
    
    数据源：AKShare的期权市场数据
    - 尝试使用 option_finance_board() 或其他期权数据接口
    
    注意：
    - AKShare对美股期权数据的支持有限
    - 此函数为实验性质，可能无法获取QQQ期权数据
    - 如果AKShare不支持，建议使用CBOE的总市场Put/Call作为替代
    
    参数:
        end_date: 指定日期（YYYY-MM-DD），None表示最新数据
    
    返回:
        标准化的字典格式，与tools.py中的拥挤度仪表盘保持一致
    """
    if not AKSHARE_AVAILABLE:
        return {
            "name": "QQQ Put/Call Ratio (AKShare)",
            "value": None,
            "notes": "AKShare库未安装，无法使用备用数据源"
        }
    
    try:
        # 尝试方案1：获取CBOE总市场Put/Call比率（作为QQQ的代理指标）
        # AKShare可能提供 option_finance_board() 或类似接口
        
        # 注意：以下代码为示例，需要根据AKShare实际API调整
        # df = ak.option_finance_board(symbol="QQQ")
        
        # 由于AKShare对美股期权支持有限，此处返回"不支持"
        raise NotImplementedError("AKShare暂不支持QQQ期权数据，建议使用CBOE总市场Put/Call作为替代")
        
    except NotImplementedError as e:
        return {
            "name": "QQQ Put/Call Ratio (AKShare)",
            "value": None,
            "notes": str(e)
        }
    except Exception as e:
        logging.error(f"AKShare Put/Call获取失败: {str(e)[:100]}")
        return {
            "name": "QQQ Put/Call Ratio (AKShare)",
            "value": None,
            "notes": f"AKShare获取失败: {str(e)[:100]}"
        }


# =====================================================
# 工具函数：测试所有AKShare数据源
# =====================================================

def test_all_akshare_sources() -> Dict[str, Any]:
    """
    测试所有AKShare备用数据源的可用性
    
    返回:
        包含每个数据源测试结果的字典
    """
    results = {
        "akshare_available": AKSHARE_AVAILABLE,
        "test_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": {}
    }
    
    if not AKSHARE_AVAILABLE:
        results["error"] = "AKShare库未安装"
        return results
    
    # 测试VIX
    print("\n[测试1/3] VIX恐慌指数...")
    vix_result = get_vix_akshare()
    results["sources"]["vix"] = {
        "success": vix_result.get("value") is not None,
        "value": vix_result.get("value"),
        "notes": vix_result.get("notes", "")
    }
    
    # 测试铜金比
    print("\n[测试2/3] 铜金比率...")
    copper_gold_result = get_copper_gold_ratio_akshare()
    results["sources"]["copper_gold_ratio"] = {
        "success": copper_gold_result.get("value") is not None,
        "value": copper_gold_result.get("value"),
        "notes": copper_gold_result.get("notes", "")
    }
    
    # 测试Put/Call
    print("\n[测试3/3] QQQ Put/Call比率...")
    put_call_result = get_qqq_put_call_akshare()
    results["sources"]["qqq_put_call"] = {
        "success": put_call_result.get("value") is not None,
        "value": put_call_result.get("value"),
        "notes": put_call_result.get("notes", "")
    }
    
    return results


if __name__ == "__main__":
    """直接运行此文件时，执行测试"""
    print("=" * 60)
    print("AKShare备用数据源测试")
    print("=" * 60)
    
    results = test_all_akshare_sources()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"AKShare库状态: {'✅ 已安装' if results['akshare_available'] else '❌ 未安装'}")
    print(f"测试时间: {results['test_timestamp']}")
    
    if results.get("sources"):
        print("\n数据源测试结果:")
        for source_name, source_result in results["sources"].items():
            status = "✅ 成功" if source_result["success"] else "❌ 失败"
            print(f"  - {source_name}: {status}")
            if source_result["value"]:
                print(f"    数据: {source_result['value']}")
            if source_result["notes"]:
                print(f"    备注: {source_result['notes']}")
    
    print("\n" + "=" * 60)

