# chart_generator.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 图表生成模块 V2.0 (Phase 3 优化版)
使用 Plotly 生成交互式可折叠图表

Phase 3 优化特性:
- 现代化渐变色设计和动画效果
- 增强的交互体验（平滑动画、懒加载）
- 优化的元数据显示（趋势指示器、变化率）
- 响应式设计，完美支持移动端
- 性能优化（渐进式加载、自适应调整）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging
try:
    from .data_manager import TimeSeriesManager, align_and_calculate_ratio
    from .tools_common import _fetch_fred_series, _fetch_yf_history, get_fred_api_key
    from .tools_L1 import _build_net_liquidity_series
    from .config import CHART_OVERLAY_PRESETS, CHART_OVERLAY_BY_FUNCTION, path_config
except ImportError:
    from data_manager import TimeSeriesManager, align_and_calculate_ratio
    from tools_common import _fetch_fred_series, _fetch_yf_history, get_fred_api_key
    from tools_L1 import _build_net_liquidity_series
    from config import CHART_OVERLAY_PRESETS, CHART_OVERLAY_BY_FUNCTION, path_config

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logging.warning("Plotly 未安装，图表功能不可用。请运行: pip install plotly")

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    logging.warning("yfinance 未安装，K线图功能不可用。")


# =====================================================
# 配置常量
# =====================================================

# 图表样式配置 - Phase 3 优化版
CHART_CONFIG = {
    "height": 450,  # 增加高度以获得更好的视觉效果
    "template": "plotly_white",
    "colors": {
        # 主题色：现代化渐变配色
        "primary": "#667eea",      # 主线颜色（紫蓝色）
        "primary_light": "#a8b3f5", # 主线浅色
        "ma20": "#f093fb",         # MA20颜色（粉紫色）
        "ma50": "#4facfe",         # MA50颜色（天蓝色）
        "percentile_10": "#ff6b6b", # 10分位线（珊瑚红）
        "percentile_90": "#51cf66", # 90分位线（翠绿）
        "percentile_area": "rgba(102, 126, 234, 0.08)",  # 分位区间（淡紫）
        "grid": "#f0f0f0",         # 网格线颜色
        "text": "#2c3e50",         # 文字颜色
        "text_light": "#7f8c8d",   # 次要文字颜色
        # 趋势指示色
        "bullish": "#00d4aa",      # 看涨（青绿）
        "bearish": "#ff6b9d",      # 看跌（粉红）
        "neutral": "#95a5a6",      # 中性（灰色）
    },
    "line_width": {
        "primary": 2.5,
        "ma": 2,
        "percentile": 1.5,
    },
    "fonts": {
        "title": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "size_title": 18,
        "size_axis": 13,
        "size_legend": 12,
    }
}

# 需要生成图表的指标映射
CHART_INDICATORS = {
    # function_id -> (cache_key, chart_type, display_name)
    "get_10y_treasury": ("DGS10", "line_with_ma", "10年期美债收益率"),
    "get_net_liquidity_momentum": ("NET_LIQUIDITY", "multi_component", "美元净流动性"),
    "get_vix": ("VIX", "line_with_ma", "VIX恐慌指数"),
    "get_vxn": ("VXN", "line_with_ma", "VXN纳指波动率"),
    "get_qqq_qqew_ratio": ("QQQ_QQEW_RATIO", "line_with_ma", "QQQ/QQEW集中度比率"),
    "get_copper_gold_ratio": ("COPPER_GOLD_RATIO", "line_with_ma", "铜金比率"),
    "get_xly_xlp_ratio": ("XLY_XLP_RATIO", "line_with_ma", "XLY/XLP风险偏好"),
    "get_10y_real_rate": ("DFII10", "line_with_ma", "10年期实际利率"),
    "get_10y_breakeven": ("T10YIE", "line_with_ma", "10年期盈亏平衡通胀率"),
    
    # V6.0 新增：量价关系指标
    "get_macd_qqq": ("MACD_QQQ", "macd_chart", "MACD动能指标"),
    "get_obv_qqq": ("OBV_QQQ", "line_with_ma", "OBV资金流向"),
    "get_volume_analysis_qqq": ("VOLUME_QQQ", "volume_chart", "QQQ成交量分析"),
    "get_donchian_channels_qqq": ("DONCHIAN_QQQ", "donchian_chart", "唐奇安通道"),
    
    # V7.0 新增：多尺度MA分析（K线图）
    "get_multi_scale_ma_position": ("QQQ_MULTI_SCALE_MA", "candlestick_with_ma", "QQQ多尺度MA分析"),
}

# CSS样式（用于HTML输出）- Phase 3 优化版
CHART_CSS = """
<style>
/* 图表容器 - 现代化卡片设计 */
.chart-container {
    margin: 24px 0;
    border: none;
    border-radius: 16px;
    padding: 0;
    background: linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%);
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.08), 
                0 1px 3px rgba(0, 0, 0, 0.05);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    position: relative;
}

.chart-container::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    opacity: 0;
    transition: opacity 0.3s ease;
}

.chart-container:hover {
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.15), 
                0 2px 8px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
}

.chart-container:hover::before {
    opacity: 1;
}

/* 图表标题 - 渐变背景 + 动画 */
.chart-title {
    font-size: 17px;
    font-weight: 700;
    cursor: pointer;
    padding: 18px 24px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 16px 16px 0 0;
    user-select: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    letter-spacing: 0.3px;
}

.chart-title::before {
    content: "📊";
    margin-right: 12px;
    font-size: 20px;
    display: inline-block;
    transition: transform 0.3s ease;
}

.chart-title::after {
    content: "▼";
    font-size: 12px;
    opacity: 0.8;
    transition: transform 0.3s ease;
    margin-left: auto;
}

details[open] .chart-title::after {
    transform: rotate(180deg);
}

.chart-title:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    padding-left: 28px;
}

.chart-title:hover::before {
    transform: scale(1.15) rotate(5deg);
}

/* 展开状态的标题 */
details[open] .chart-title {
    border-radius: 16px 16px 0 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
}

/* 图表内容区 - 优雅的内边距和背景 */
.chart-content {
    padding: 24px;
    background: linear-gradient(180deg, #fafbfc 0%, #ffffff 100%);
    border-radius: 0 0 16px 16px;
    animation: slideDown 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes slideDown {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* 图表元数据 - 信息卡片 */
.chart-meta {
    font-size: 13px;
    color: #5a6c7d;
    margin-top: 16px;
    padding: 14px 18px;
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border-radius: 12px;
    border-left: 4px solid #667eea;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.chart-meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
}

.chart-meta-label {
    font-weight: 600;
    color: #2c3e50;
}

.chart-meta-value {
    color: #667eea;
    font-weight: 500;
}

/* 趋势指示器 */
.trend-indicator {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    margin-left: 8px;
}

.trend-up {
    background: linear-gradient(135deg, #00d4aa 0%, #00b894 100%);
    color: white;
}

.trend-down {
    background: linear-gradient(135deg, #ff6b9d 0%, #ee5a6f 100%);
    color: white;
}

.trend-neutral {
    background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
    color: white;
}

/* 展开/折叠所有按钮 - 现代化设计 */
.expand-all-charts {
    margin: 24px 0;
    padding: 14px 28px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 600;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    letter-spacing: 0.5px;
    display: inline-flex;
    align-items: center;
    gap: 10px;
}

.expand-all-charts::before {
    content: "📊";
    font-size: 18px;
}

.expand-all-charts:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    box-shadow: 0 6px 25px rgba(102, 126, 234, 0.4);
    transform: translateY(-2px);
}

.expand-all-charts:active {
    transform: translateY(0);
    box-shadow: 0 2px 10px rgba(102, 126, 234, 0.3);
}

/* 响应式设计 */
@media (max-width: 768px) {
    .chart-container {
        margin: 16px 0;
        border-radius: 12px;
    }
    
    .chart-title {
        font-size: 15px;
        padding: 14px 18px;
    }
    
    .chart-content {
        padding: 16px;
    }
    
    .chart-meta {
        font-size: 12px;
        padding: 12px 14px;
        flex-direction: column;
        gap: 10px;
    }
    
    .expand-all-charts {
        width: 100%;
        justify-content: center;
    }
}

/* 加载动画 */
@keyframes pulse {
    0%, 100% {
        opacity: 1;
    }
    50% {
        opacity: 0.5;
    }
}

.chart-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: #667eea;
    font-size: 14px;
    animation: pulse 1.5s ease-in-out infinite;
}

/* 无数据提示 */
.chart-no-data {
    padding: 40px;
    text-align: center;
    color: #95a5a6;
    font-size: 14px;
}

.chart-no-data::before {
    content: "📭";
    display: block;
    font-size: 48px;
    margin-bottom: 12px;
    opacity: 0.5;
}

/* Plotly图表容器优化 */
.plotly-graph-div {
    border-radius: 8px;
    overflow: hidden;
}

/* 滚动条美化 */
.chart-content::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

.chart-content::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
}

.chart-content::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 4px;
}

.chart-content::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
}
</style>
"""

DEFAULT_CACHE_DIR = Path(path_config.cache_dir)


# =====================================================
# 核心图表生成函数
# =====================================================

def generate_chart_html(
    indicator_name: str,
    df: pd.DataFrame,
    chart_type: str = "line",
    show_ma: bool = True,
    show_percentiles: bool = False,
    percentile_data: Optional[Dict[str, float]] = None
) -> str:
    """
    生成单个指标的可折叠HTML图表
    
    参数:
        indicator_name: 指标名称
        df: 包含 ['date', 'value'] 的DataFrame
        chart_type: 图表类型 ('line', 'line_with_ma', 'multi_component')
        show_ma: 是否显示移动平均线
        show_percentiles: 是否显示百分位区间
        percentile_data: 百分位数据 {'p10': value, 'p90': value}
    
    返回:
        HTML字符串（包含<details>标签）
    """
    if not PLOTLY_AVAILABLE:
        return f"""
        <div class="chart-container" style="padding: 16px;">
            <p style="color: #d32f2f;">⚠️ 图表功能不可用：Plotly未安装</p>
            <p style="font-size: 12px; color: #666;">请运行: pip install plotly</p>
        </div>
        """
    
    if df is None or df.empty:
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                <p style="color: #ff9800;">⚠️ 暂无历史数据</p>
            </div>
        </details>
        """
    
    try:
        df = df.copy()
        df = df.loc[:, ~df.columns.duplicated()]
        if 'date' not in df.columns or 'value' not in df.columns:
            raise ValueError("数据格式错误：缺少 date/value 列")
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['date', 'value'])
        df = df.sort_values('date').drop_duplicates(subset=['date'], keep='last').reset_index(drop=True)
        
        # 创建图表
        fig = go.Figure()
        
        # 主线 - 渐变填充效果
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['value'],
            mode='lines',
            name=indicator_name,
            line=dict(
                color=CHART_CONFIG['colors']['primary'],
                width=CHART_CONFIG['line_width']['primary'],
                shape='spline'  # 平滑曲线
            ),
            fill='tozeroy',
            fillcolor=CHART_CONFIG['colors']['percentile_area'],
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>' +
                         f'<span style="color:{CHART_CONFIG["colors"]["primary"]}">●</span> ' +
                         '数值: <b>%{y:.4f}</b><extra></extra>'
        ))
        
        # 添加MA20趋势线
        if show_ma and len(df) >= 20:
            ma20 = df['value'].rolling(window=20, min_periods=20).mean()
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=ma20,
                mode='lines',
                name='MA20 (20日均线)',
                line=dict(
                    color=CHART_CONFIG['colors']['ma20'],
                    width=CHART_CONFIG['line_width']['ma'],
                    dash='dash',
                    shape='spline'
                ),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>' +
                             f'<span style="color:{CHART_CONFIG["colors"]["ma20"]}">●</span> ' +
                             'MA20: <b>%{y:.4f}</b><extra></extra>'
            ))
        
        # 添加MA50趋势线（如果数据足够）
        if show_ma and len(df) >= 50:
            ma50 = df['value'].rolling(window=50, min_periods=50).mean()
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=ma50,
                mode='lines',
                name='MA50 (50日均线)',
                line=dict(
                    color=CHART_CONFIG['colors']['ma50'],
                    width=CHART_CONFIG['line_width']['ma'],
                    dash='dot',
                    shape='spline'
                ),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>' +
                             f'<span style="color:{CHART_CONFIG["colors"]["ma50"]}">●</span> ' +
                             'MA50: <b>%{y:.4f}</b><extra></extra>'
            ))
        
        # 添加百分位区间
        if show_percentiles and percentile_data:
            p10 = percentile_data.get('p10')
            p90 = percentile_data.get('p90')
            p50 = percentile_data.get('p50')
            
            if p10 is not None and p90 is not None:
                # 10-90分位区间
                fig.add_hrect(
                    y0=p10, y1=p90,
                    fillcolor=CHART_CONFIG['colors']['percentile_area'],
                    opacity=0.15,
                    layer="below",
                    line_width=0,
                    annotation_text="10-90分位区间",
                    annotation_position="top left",
                    annotation=dict(
                        font_size=11, 
                        font_color=CHART_CONFIG['colors']['text_light'],
                        bgcolor="rgba(255,255,255,0.8)",
                        borderpad=4
                    )
                )
                
                # 添加中位线
                if p50 is not None:
                    fig.add_hline(
                        y=p50,
                        line_dash="dot",
                        line_color=CHART_CONFIG['colors']['neutral'],
                        line_width=1,
                        opacity=0.5,
                        annotation_text="中位数",
                        annotation_position="right",
                        annotation=dict(
                            font_size=10,
                            font_color=CHART_CONFIG['colors']['text_light']
                        )
                    )
        
        # 布局设置 - Phase 3 优化版
        fig.update_layout(
            title=dict(
                text=f"<b>{indicator_name}</b> 历史趋势分析",
                font=dict(
                    size=CHART_CONFIG['fonts']['size_title'],
                    color=CHART_CONFIG['colors']['text'],
                    family=CHART_CONFIG['fonts']['title']
                ),
                x=0.02,
                xanchor='left'
            ),
            xaxis=dict(
                title="",
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                gridwidth=1,
                zeroline=False,
                showline=True,
                linewidth=1,
                linecolor='#e0e0e0',
                tickfont=dict(
                    size=CHART_CONFIG['fonts']['size_axis'],
                    color=CHART_CONFIG['colors']['text_light']
                ),
                rangeslider=dict(visible=False)  # 禁用范围滑块以节省空间
            ),
            yaxis=dict(
                title="",
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                gridwidth=1,
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='#d0d0d0',
                showline=True,
                linewidth=1,
                linecolor='#e0e0e0',
                tickfont=dict(
                    size=CHART_CONFIG['fonts']['size_axis'],
                    color=CHART_CONFIG['colors']['text_light']
                )
            ),
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor="white",
                font_size=13,
                font_family=CHART_CONFIG['fonts']['body'],
                bordercolor=CHART_CONFIG['colors']['primary']
            ),
            template=CHART_CONFIG['template'],
            height=CHART_CONFIG['height'],
            margin=dict(l=60, r=40, t=70, b=50),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor=CHART_CONFIG['colors']['grid'],
                borderwidth=1,
                font=dict(
                    size=CHART_CONFIG['fonts']['size_legend'],
                    color=CHART_CONFIG['colors']['text']
                )
            ),
            plot_bgcolor='rgba(250,251,252,0.5)',
            paper_bgcolor='white',
            font=dict(
                family=CHART_CONFIG['fonts']['body'],
                color=CHART_CONFIG['colors']['text']
            )
        )
        
        # 转换为HTML - Phase 3 优化配置
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_{indicator_name.replace(' ', '_').replace('/', '_')}",
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'{indicator_name}_chart',
                    'height': 800,
                    'width': 1400,
                    'scale': 2
                },
                'responsive': True,  # 响应式设计
                'scrollZoom': True,  # 启用滚轮缩放
            }
        )
        
        # 生成增强的元数据 - Phase 3 优化版
        latest_value = df['value'].iloc[-1]
        latest_date = df['date'].iloc[-1].strftime('%Y-%m-%d')
        data_points = len(df)
        date_range_start = df['date'].iloc[0].strftime('%Y-%m-%d')
        date_range_end = latest_date
        
        # 计算趋势
        if len(df) >= 20:
            ma20_latest = df['value'].rolling(window=20).mean().iloc[-1]
            trend = "上涨" if latest_value > ma20_latest else "下跌"
            trend_class = "trend-up" if latest_value > ma20_latest else "trend-down"
            trend_icon = "📈" if latest_value > ma20_latest else "📉"
        else:
            trend = "中性"
            trend_class = "trend-neutral"
            trend_icon = "➡️"
        
        # 计算变化率
        if len(df) >= 2:
            prev_value = df['value'].iloc[-2]
            if pd.notna(prev_value) and prev_value != 0:
                change_pct = ((latest_value - prev_value) / prev_value) * 100
                change_text = f"{change_pct:+.2f}%"
            else:
                change_text = "N/A"
        else:
            change_text = "N/A"
        
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">最新值:</span>
                <span class="chart-meta-value">{latest_value:.4f}</span>
                <span class="trend-indicator {trend_class}">{trend_icon} {trend}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">日期:</span>
                <span class="chart-meta-value">{latest_date}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">日变化:</span>
                <span class="chart-meta-value">{change_text}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">数据点:</span>
                <span class="chart-meta-value">{data_points}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">时间范围:</span>
                <span class="chart-meta-value">{date_range_start} ~ {date_range_end}</span>
            </div>
        </div>
        """
        
        # 包装在<details>标签中
        collapsible_html = f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
        
        return collapsible_html
        
    except Exception as e:
        logging.error(f"生成图表失败 ({indicator_name}): {str(e)}")
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                <p style="color: #d32f2f;">❌ 图表生成失败: {str(e)}</p>
            </div>
        </details>
        """


def generate_multi_component_chart(
    indicator_name: str,
    components: Dict[str, pd.DataFrame],
    highlight_component: Optional[str] = None
) -> str:
    """
    生成多组件对比图表（如Net Liquidity的WALCL, TGA, RRP）
    
    参数:
        indicator_name: 指标名称
        components: 组件数据字典 {'component_name': DataFrame}
        highlight_component: 需要高亮的组件名称
    
    返回:
        HTML字符串
    """
    if not PLOTLY_AVAILABLE or not components:
        return ""
    
    try:
        fig = go.Figure()
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        for idx, (comp_name, df) in enumerate(components.items()):
            if df is None or df.empty:
                continue
            
            df['date'] = pd.to_datetime(df['date'])
            
            # 高亮组件使用更粗的线条
            line_width = 3 if comp_name == highlight_component else 2
            
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['value'],
                mode='lines',
                name=comp_name,
                line=dict(
                    color=colors[idx % len(colors)],
                    width=line_width
                ),
                hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{comp_name}: %{{y:.2f}}<extra></extra>'
            ))
        
        fig.update_layout(
            title=f"{indicator_name} 组件对比",
            xaxis_title="日期",
            yaxis_title="数值（十亿美元）",
            hovermode='x unified',
            template='plotly_white',
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_{indicator_name.replace(' ', '_')}",
            config={'displayModeBar': True, 'displaylogo': False}
        )
        
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 组件趋势</summary>
            <div class="chart-content">
                {chart_html}
            </div>
        </details>
        """
        
    except Exception as e:
        logging.error(f"生成多组件图表失败 ({indicator_name}): {str(e)}")
        return ""


def generate_macd_chart(
    indicator_name: str,
    df: pd.DataFrame
) -> str:
    """
    生成MACD专用图表（包含MACD线、信号线和柱状图）
    
    参数:
        indicator_name: 指标名称
        df: 包含 ['date', 'macd', 'signal', 'histogram'] 的DataFrame
    
    返回:
        HTML字符串
    """
    if not PLOTLY_AVAILABLE or df is None or df.empty:
        return ""
    
    try:
        df['date'] = pd.to_datetime(df['date'])
        
        # 创建子图：上方MACD线，下方柱状图
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=('MACD线与信号线', 'MACD柱状图（动能）')
        )
        
        # 上图：MACD线和信号线
        fig.add_trace(
            go.Scatter(
                x=df['date'],
                y=df['macd'],
                mode='lines',
                name='MACD',
                line=dict(color=CHART_CONFIG['colors']['primary'], width=2),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>MACD: %{y:.3f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df['date'],
                y=df['signal'],
                mode='lines',
                name='信号线',
                line=dict(color=CHART_CONFIG['colors']['ma20'], width=2, dash='dash'),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>信号线: %{y:.3f}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # 下图：柱状图（红绿着色）
        colors_hist = [CHART_CONFIG['colors']['bullish'] if val >= 0 else CHART_CONFIG['colors']['bearish'] 
                       for val in df['histogram']]
        
        fig.add_trace(
            go.Bar(
                x=df['date'],
                y=df['histogram'],
                name='柱状图',
                marker_color=colors_hist,
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>柱状图: %{y:.3f}<extra></extra>'
            ),
            row=2, col=1
        )
        
        # 添加零轴线
        fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1, row=1, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="gray", line_width=1, row=2, col=1)
        
        fig.update_layout(
            title=dict(
                text=f"<b>{indicator_name}</b> 动能分析",
                font=dict(size=18, color=CHART_CONFIG['colors']['text'])
            ),
            hovermode='x unified',
            template='plotly_white',
            height=550,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_xaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        fig.update_yaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_macd_{indicator_name.replace(' ', '_')}",
            config={'displayModeBar': True, 'displaylogo': False, 'responsive': True}
        )
        
        # 生成元数据
        latest_macd = df['macd'].iloc[-1]
        latest_signal = df['signal'].iloc[-1]
        latest_hist = df['histogram'].iloc[-1]
        latest_date = df['date'].iloc[-1].strftime('%Y-%m-%d')
        
        crossover = "金叉(看涨)" if latest_macd > latest_signal else "死叉(看跌)"
        momentum = "正向动能" if latest_hist > 0 else "负向动能"
        
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">MACD:</span>
                <span class="chart-meta-value">{latest_macd:.3f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">信号线:</span>
                <span class="chart-meta-value">{latest_signal:.3f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">柱状图:</span>
                <span class="chart-meta-value">{latest_hist:.3f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">状态:</span>
                <span class="chart-meta-value">{crossover} | {momentum}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">日期:</span>
                <span class="chart-meta-value">{latest_date}</span>
            </div>
        </div>
        """
        
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
        
    except Exception as e:
        logging.error(f"生成MACD图表失败 ({indicator_name}): {str(e)}")
        return ""


def generate_volume_chart(
    indicator_name: str,
    df: pd.DataFrame
) -> str:
    """
    生成成交量专用图表（柱状图+均线）
    
    参数:
        indicator_name: 指标名称
        df: 包含 ['date', 'volume', 'volume_ma20'] 的DataFrame
    
    返回:
        HTML字符串
    """
    if not PLOTLY_AVAILABLE or df is None or df.empty:
        return ""
    
    try:
        df['date'] = pd.to_datetime(df['date'])
        
        fig = go.Figure()
        
        # 成交量柱状图
        fig.add_trace(go.Bar(
            x=df['date'],
            y=df['volume'],
            name='成交量',
            marker_color=CHART_CONFIG['colors']['primary'],
            opacity=0.6,
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>成交量: %{y:,.0f}<extra></extra>'
        ))
        
        # 20日均量线
        if 'volume_ma20' in df.columns:
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['volume_ma20'],
                mode='lines',
                name='20日均量',
                line=dict(color=CHART_CONFIG['colors']['ma20'], width=2),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>20日均量: %{y:,.0f}<extra></extra>'
            ))
        
        fig.update_layout(
            title=dict(
                text=f"<b>{indicator_name}</b> 历史趋势",
                font=dict(size=18, color=CHART_CONFIG['colors']['text'])
            ),
            xaxis_title="",
            yaxis_title="成交量",
            hovermode='x unified',
            template='plotly_white',
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_xaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        fig.update_yaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_volume_{indicator_name.replace(' ', '_')}",
            config={'displayModeBar': True, 'displaylogo': False, 'responsive': True}
        )
        
        # 生成元数据
        latest_volume = df['volume'].iloc[-1]
        latest_ma = df['volume_ma20'].iloc[-1] if 'volume_ma20' in df.columns else 0
        latest_date = df['date'].iloc[-1].strftime('%Y-%m-%d')
        ratio = (latest_volume / latest_ma) if latest_ma > 0 else 0
        
        volume_status = "放量" if ratio > 1.2 else ("缩量" if ratio < 0.8 else "正常")
        
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">当前成交量:</span>
                <span class="chart-meta-value">{latest_volume:,.0f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">20日均量:</span>
                <span class="chart-meta-value">{latest_ma:,.0f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">量比:</span>
                <span class="chart-meta-value">{ratio:.2f}x</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">状态:</span>
                <span class="chart-meta-value">{volume_status}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">日期:</span>
                <span class="chart-meta-value">{latest_date}</span>
            </div>
        </div>
        """
        
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
        
    except Exception as e:
        logging.error(f"生成成交量图表失败 ({indicator_name}): {str(e)}")
        return ""


def generate_donchian_chart(
    indicator_name: str,
    df: pd.DataFrame
) -> str:
    """
    生成唐奇安通道专用图表（价格+上下轨）
    
    参数:
        indicator_name: 指标名称
        df: 包含 ['date', 'close', 'upper_band', 'lower_band'] 的DataFrame
    
    返回:
        HTML字符串
    """
    if not PLOTLY_AVAILABLE or df is None or df.empty:
        return ""
    
    try:
        df['date'] = pd.to_datetime(df['date'])
        
        fig = go.Figure()
        
        # 价格线
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['close'],
            mode='lines',
            name='QQQ价格',
            line=dict(color=CHART_CONFIG['colors']['primary'], width=2.5),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>价格: $%{y:.2f}<extra></extra>'
        ))
        
        # 上轨
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['upper_band'],
            mode='lines',
            name='上轨(20日高点)',
            line=dict(color=CHART_CONFIG['colors']['percentile_90'], width=1.5, dash='dash'),
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>上轨: $%{y:.2f}<extra></extra>'
        ))
        
        # 下轨
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['lower_band'],
            mode='lines',
            name='下轨(20日低点)',
            line=dict(color=CHART_CONFIG['colors']['percentile_10'], width=1.5, dash='dash'),
            fill='tonexty',
            fillcolor='rgba(102, 126, 234, 0.1)',
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>下轨: $%{y:.2f}<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(
                text=f"<b>{indicator_name}</b> 趋势跟踪系统",
                font=dict(size=18, color=CHART_CONFIG['colors']['text'])
            ),
            xaxis_title="",
            yaxis_title="价格 (USD)",
            hovermode='x unified',
            template='plotly_white',
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_xaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        fig.update_yaxes(showgrid=True, gridcolor=CHART_CONFIG['colors']['grid'])
        
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_donchian_{indicator_name.replace(' ', '_')}",
            config={'displayModeBar': True, 'displaylogo': False, 'responsive': True}
        )
        
        # 生成元数据
        latest_close = df['close'].iloc[-1]
        latest_upper = df['upper_band'].iloc[-1]
        latest_lower = df['lower_band'].iloc[-1]
        latest_date = df['date'].iloc[-1].strftime('%Y-%m-%d')
        
        channel_width = latest_upper - latest_lower
        position_pct = ((latest_close - latest_lower) / channel_width * 100) if channel_width > 0 else 50
        
        if latest_close > latest_upper:
            position_status = "突破上轨(强势)"
        elif latest_close < latest_lower:
            position_status = "跌破下轨(弱势)"
        else:
            position_status = f"通道内({position_pct:.0f}%位置)"
        
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">当前价格:</span>
                <span class="chart-meta-value">${latest_close:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">上轨:</span>
                <span class="chart-meta-value">${latest_upper:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">下轨:</span>
                <span class="chart-meta-value">${latest_lower:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">通道宽度:</span>
                <span class="chart-meta-value">${channel_width:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">位置状态:</span>
                <span class="chart-meta-value">{position_status}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">日期:</span>
                <span class="chart-meta-value">{latest_date}</span>
            </div>
        </div>
        """
        
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 趋势图表</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
        
    except Exception as e:
        logging.error(f"生成唐奇安通道图表失败 ({indicator_name}): {str(e)}")
        return ""


def generate_multi_component_chart(
    indicator_name: str,
    components: Dict[str, pd.DataFrame],
    highlight_component: Optional[str] = None
) -> str:
    """
    生成多组件对比图表（如Net Liquidity的WALCL, TGA, RRP）
    
    参数:
        indicator_name: 指标名称
        components: 组件数据字典 {'component_name': DataFrame}
        highlight_component: 需要高亮的组件名称
    
    返回:
        HTML字符串
    """
    if not PLOTLY_AVAILABLE or not components:
        return ""
    
    try:
        fig = go.Figure()
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
        
        for idx, (comp_name, df) in enumerate(components.items()):
            if df is None or df.empty:
                continue
            
            df['date'] = pd.to_datetime(df['date'])
            
            # 高亮组件使用更粗的线条
            line_width = 3 if comp_name == highlight_component else 2
            
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['value'],
                mode='lines',
                name=comp_name,
                line=dict(
                    color=colors[idx % len(colors)],
                    width=line_width
                ),
                hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>{comp_name}: %{{y:.2f}}<extra></extra>'
            ))
        
        fig.update_layout(
            title=f"{indicator_name} 组件对比",
            xaxis_title="日期",
            yaxis_title="数值（十亿美元）",
            hovermode='x unified',
            template='plotly_white',
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_{indicator_name.replace(' ', '_')}",
            config={'displayModeBar': True, 'displaylogo': False}
        )
        
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name} 组件趋势</summary>
            <div class="chart-content">
                {chart_html}
            </div>
        </details>
        """
        
    except Exception as e:
        logging.error(f"生成多组件图表失败 ({indicator_name}): {str(e)}")
        return ""


# =====================================================
# 数据获取辅助函数
# =====================================================

def get_historical_data_from_cache(
    cache_key: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lookback_days: int = 365
) -> Optional[pd.DataFrame]:
    """
    从TimeSeriesManager缓存中读取历史数据
    
    参数:
        cache_key: 缓存文件的key（如 "DGS10", "VIX"）
        cache_dir: 缓存目录路径
        lookback_days: 回溯天数（默认1年）
    
    返回:
        包含 ['date', 'value'] 的DataFrame，如果失败返回None
    """
    try:
        _refresh_chart_cache(cache_key, cache_dir, lookback_days)
        cache_file = cache_dir / f"{cache_key}.csv"
        
        if not cache_file.exists():
            logging.warning(f"缓存文件不存在: {cache_file}")
            return None
        
        df = pd.read_csv(cache_file)
        
        # 确保有必要的列
        if 'date' not in df.columns or 'value' not in df.columns:
            logging.warning(f"缓存文件格式错误: {cache_file}")
            return None
        
        df['date'] = pd.to_datetime(df['date'])
        
        # 只取最近的数据
        if lookback_days > 0:
            cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
            df = df[df['date'] >= cutoff_date]
        
        df = df.sort_values('date').reset_index(drop=True)
        
        logging.info(f"成功从缓存读取 {cache_key}: {len(df)} 条记录")
        return df[['date', 'value']]
        
    except Exception as e:
        logging.error(f"读取缓存失败 ({cache_key}): {str(e)}")
        return None


def _refresh_chart_cache(cache_key: str, cache_dir: Path, lookback_days: int) -> None:
    try:
        if cache_key in {"QQQ_QQEW_RATIO", "XLY_XLP_RATIO", "COPPER_GOLD_RATIO"}:
            _refresh_ratio_cache(cache_key, cache_dir, lookback_days)
            return
        if cache_key == "NET_LIQUIDITY":
            net_liq_df, _, _, _ = _build_net_liquidity_series()
            if net_liq_df is None or net_liq_df.empty:
                return
            if lookback_days > 0:
                cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
                net_liq_df = net_liq_df[net_liq_df["date"] >= cutoff_date]
            _write_cache_df(cache_key, net_liq_df, cache_dir)
            return
        _update_cache_series(cache_key, cache_dir)
    except Exception as e:
        logging.warning(f"图表缓存刷新失败 ({cache_key}): {str(e)}")


def _update_cache_series(cache_key: str, cache_dir: Path) -> None:
    manager = TimeSeriesManager(cache_dir=str(cache_dir))
    fred_map = {"DGS10": "DGS10", "DFII10": "DFII10", "T10YIE": "T10YIE"}
    yf_map = {"VIX": "^VIX", "VXN": "^VXN"}
    if cache_key in fred_map:
        if not get_fred_api_key():
            return
        series_id = fred_map[cache_key]
        manager.get_or_update_series(series_id, lambda start_date: _fetch_fred_series(series_id, start_date=start_date))
        return
    if cache_key in yf_map:
        ticker = yf_map[cache_key]
        manager.get_or_update_series(cache_key, lambda start_date: _fetch_yf_history(ticker, start_date=start_date))
        return


def _refresh_ratio_cache(cache_key: str, cache_dir: Path, lookback_days: int) -> None:
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(days=lookback_days)
    if cache_key == "QQQ_QQEW_RATIO":
        numerator_df = _fetch_yf_history("QQQ", start_date=start_date)
        denominator_df = _fetch_yf_history("QQEW", start_date=start_date)
    elif cache_key == "XLY_XLP_RATIO":
        numerator_df = _fetch_yf_history("XLY", start_date=start_date)
        denominator_df = _fetch_yf_history("XLP", start_date=start_date)
    elif cache_key == "COPPER_GOLD_RATIO":
        numerator_df = _fetch_yf_history("HG=F", start_date=start_date)
        denominator_df = _fetch_yf_history("GC=F", start_date=start_date)
    else:
        return
    if numerator_df is None or denominator_df is None or numerator_df.empty or denominator_df.empty:
        return
    ratio_df = align_and_calculate_ratio(
        numerator_series=numerator_df[["date", "value"]],
        denominator_series=denominator_df[["date", "value"]],
        date_col="date",
        value_col="value",
    )
    if ratio_df is None or ratio_df.empty:
        return
    ratio_series = ratio_df.rename(columns={"ratio": "value"})[["date", "value"]]
    _write_cache_df(cache_key, ratio_series, cache_dir)


def _write_cache_df(cache_key: str, df: pd.DataFrame, cache_dir: Path) -> None:
    if df is None or df.empty:
        return
    if "date" not in df.columns or "value" not in df.columns:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_df = df[["date", "value"]].copy()
    output_df["date"] = pd.to_datetime(output_df["date"])
    output_df = output_df.sort_values("date").reset_index(drop=True)
    output_df.to_csv(cache_dir / f"{cache_key}.csv", index=False)


def calculate_percentiles_from_data(df: pd.DataFrame) -> Dict[str, float]:
    """
    从历史数据计算百分位
    
    参数:
        df: 包含 'value' 列的DataFrame
    
    返回:
        百分位字典 {'p10': value, 'p25': value, 'p50': value, 'p75': value, 'p90': value}
    """
    if df is None or df.empty or 'value' not in df.columns:
        return {}
    
    try:
        percentiles = {
            'p10': df['value'].quantile(0.10),
            'p25': df['value'].quantile(0.25),
            'p50': df['value'].quantile(0.50),
            'p75': df['value'].quantile(0.75),
            'p90': df['value'].quantile(0.90),
        }
        return percentiles
    except Exception as e:
        logging.error(f"计算百分位失败: {str(e)}")
        return {}


def _apply_series_transform(values: pd.Series, transform: str) -> pd.Series:
    if values is None or values.empty:
        return values
    clean = values.dropna()
    if clean.empty:
        return values
    if transform == "zscore":
        mean = clean.mean()
        std = clean.std(ddof=0)
        if std == 0:
            return values * 0
        return (values - mean) / std
    if transform == "minmax":
        min_val = clean.min()
        max_val = clean.max()
        if max_val == min_val:
            return values * 0
        return (values - min_val) / (max_val - min_val)
    if transform == "index_100":
        base = clean.iloc[0]
        if base == 0:
            return values * 0
        return (values / base) * 100
    return values


def generate_overlay_chart_for_indicator(
    function_id: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lookback_days: int = 365
) -> str:
    if not PLOTLY_AVAILABLE:
        return ""
    overlay_keys = CHART_OVERLAY_BY_FUNCTION.get(function_id, [])
    if not overlay_keys:
        return ""
    option_items = ['<option value="all">全部叠加</option>', '<option value="none">隐藏叠加</option>']
    for overlay_key in overlay_keys:
        preset = CHART_OVERLAY_PRESETS.get(overlay_key, {})
        label = preset.get("title", overlay_key)
        option_items.append(f'<option value="{overlay_key}">{label}</option>')
    overlay_selector_id = f"overlay-filter-{function_id}"
    overlays_html = f"""
    <div style="margin:12px 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <div style="font-weight:600;color:#4a5568;">叠加切换</div>
        <select id="{overlay_selector_id}" style="padding:6px 10px;border-radius:8px;border:1px solid #e2e8f0;background:#fff;">
            {''.join(option_items)}
        </select>
    </div>
    <script>
    (function() {{
        const select = document.getElementById("{overlay_selector_id}");
        if (!select) return;
        const apply = () => {{
            const val = select.value;
            const items = document.querySelectorAll('.overlay-chart[data-overlay-for="{function_id}"]');
            items.forEach(el => {{
                if (val === "all") {{
                    el.style.display = "";
                }} else if (val === "none") {{
                    el.style.display = "none";
                }} else {{
                    el.style.display = el.dataset.overlayKey === val ? "" : "none";
                }}
            }});
        }};
        select.addEventListener("change", apply);
        apply();
    }})();
    </script>
    """
    for overlay_key in overlay_keys:
        overlay_config = CHART_OVERLAY_PRESETS.get(overlay_key)
        if not overlay_config:
            continue
        fig = go.Figure()
        start_dates = []
        end_dates = []
        has_data = False
        transform = overlay_config.get("transform", "raw")
        colors = [
            CHART_CONFIG['colors']['primary'],
            CHART_CONFIG['colors']['ma20'],
            CHART_CONFIG['colors']['ma50'],
            CHART_CONFIG['colors']['percentile_90'],
            CHART_CONFIG['colors']['percentile_10'],
        ]
        for idx, item in enumerate(overlay_config.get("series", [])):
            df = get_historical_data_from_cache(item["cache_key"], cache_dir, lookback_days)
            if df is None or df.empty:
                continue
            df = df.copy()
            df = df.loc[:, ~df.columns.duplicated()]
            if 'date' not in df.columns or 'value' not in df.columns:
                continue
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df = df.dropna(subset=['date', 'value'])
            df = df.sort_values('date').drop_duplicates(subset=['date'], keep='last')
            if df.empty:
                continue
            df['value'] = _apply_series_transform(df['value'], transform)
            has_data = True
            start_dates.append(df['date'].iloc[0])
            end_dates.append(df['date'].iloc[-1])
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['value'],
                mode='lines',
                name=item["name"],
                line=dict(color=colors[idx % len(colors)], width=2),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>' + f'{item["name"]}: <b>%{{y:.4f}}</b><extra></extra>'
            ))
        if not has_data:
            continue
        fig.update_layout(
            title=dict(
                text=f"<b>{overlay_config['title']}</b>",
                font=dict(
                    size=CHART_CONFIG['fonts']['size_title'],
                    color=CHART_CONFIG['colors']['text'],
                    family=CHART_CONFIG['fonts']['title']
                ),
                x=0.02,
                xanchor='left'
            ),
            xaxis=dict(
                title="",
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                gridwidth=1,
                zeroline=False,
                showline=True,
                linewidth=1,
                linecolor='#e0e0e0',
                tickfont=dict(
                    size=CHART_CONFIG['fonts']['size_axis'],
                    color=CHART_CONFIG['colors']['text_light']
                ),
            ),
            yaxis=dict(
                title="",
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                gridwidth=1,
                zeroline=True,
                zerolinewidth=1,
                zerolinecolor='#d0d0d0',
                showline=True,
                linewidth=1,
                linecolor='#e0e0e0',
                tickfont=dict(
                    size=CHART_CONFIG['fonts']['size_axis'],
                    color=CHART_CONFIG['colors']['text_light']
                )
            ),
            hovermode='x unified',
            template=CHART_CONFIG['template'],
            height=CHART_CONFIG['height'],
            margin=dict(l=60, r=40, t=70, b=50),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor=CHART_CONFIG['colors']['grid'],
                borderwidth=1,
                font=dict(
                    size=CHART_CONFIG['fonts']['size_legend'],
                    color=CHART_CONFIG['colors']['text']
                )
            ),
            plot_bgcolor='rgba(250,251,252,0.5)',
            paper_bgcolor='white',
            font=dict(
                family=CHART_CONFIG['fonts']['body'],
                color=CHART_CONFIG['colors']['text']
            )
        )
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_overlay_{function_id}_{overlay_key}",
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'responsive': True,
                'scrollZoom': True,
            }
        )
        date_range_start = min(start_dates).strftime('%Y-%m-%d')
        date_range_end = max(end_dates).strftime('%Y-%m-%d')
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">时间范围:</span>
                <span class="chart-meta-value">{date_range_start} ~ {date_range_end}</span>
            </div>
        </div>
        """
        overlays_html += f"""
        <details class="chart-container overlay-chart" data-overlay-key="{overlay_key}" data-overlay-for="{function_id}">
            <summary class="chart-title">{overlay_config['title']}</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
    return overlays_html


# =====================================================
# 批量图表生成
# =====================================================

def generate_charts_for_indicators(
    indicators_data: List[Dict[str, Any]],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lookback_days: int = 365
) -> Dict[str, str]:
    """
    为多个指标批量生成图表
    
    参数:
        indicators_data: 指标数据列表（来自data_collected_v9_live.json）
        cache_dir: 缓存目录
        lookback_days: 回溯天数
    
    返回:
        字典 {function_id: chart_html}
    """
    charts = {}
    
    for indicator in indicators_data:
        function_id = indicator.get('function_id')
        
        if function_id not in CHART_INDICATORS:
            continue
        
        cache_key, chart_type, display_name = CHART_INDICATORS[function_id]
        
        # 获取历史数据
        df = get_historical_data_from_cache(cache_key, cache_dir, lookback_days)
        
        if df is None or df.empty:
            logging.warning(f"跳过图表生成 ({display_name}): 无历史数据")
            continue
        
        # 计算百分位（用于着色）
        percentiles = calculate_percentiles_from_data(df)
        
        # 生成图表
        if chart_type == "multi_component":
            # 特殊处理：Net Liquidity需要多组件图表
            # 这里暂时使用单线图，后续可以扩展
            chart_html = generate_chart_html(
                indicator_name=display_name,
                df=df,
                chart_type="line",
                show_ma=True,
                show_percentiles=True,
                percentile_data=percentiles
            )
        elif chart_type == "macd_chart":
            # MACD专用图表
            chart_html = generate_macd_chart(indicator_name=display_name, df=df)
        elif chart_type == "volume_chart":
            # 成交量专用图表
            chart_html = generate_volume_chart(indicator_name=display_name, df=df)
        elif chart_type == "donchian_chart":
            # 唐奇安通道专用图表
            chart_html = generate_donchian_chart(indicator_name=display_name, df=df)
        else:
            chart_html = generate_chart_html(
                indicator_name=display_name,
                df=df,
                chart_type=chart_type,
                show_ma=True,
                show_percentiles=True,
                percentile_data=percentiles
            )
        
        charts[function_id] = chart_html
        logging.info(f"✓ 生成图表: {display_name}")
    
    return charts


def get_chart_css() -> str:
    """返回图表CSS样式"""
    return CHART_CSS


def get_expand_all_button_script() -> str:
    """返回"展开所有图表"按钮的JavaScript - Phase 3 优化版"""
    return """
    <script>
    // 展开/折叠所有图表
    function toggleAllCharts() {
        const details = document.querySelectorAll('.chart-container');
        const allOpen = Array.from(details).every(d => d.open);
        
        details.forEach((detail, index) => {
            setTimeout(() => {
                detail.open = !allOpen;
            }, index * 50);  // 添加渐进式动画效果
        });
        
        const button = document.querySelector('.expand-all-charts');
        button.textContent = allOpen ? '📊 展开所有图表' : '📊 折叠所有图表';
    }
    
    // 平滑滚动到图表
    function scrollToChart(chartId) {
        const element = document.getElementById(chartId);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
    
    // 图表懒加载优化
    document.addEventListener('DOMContentLoaded', function() {
        const chartContainers = document.querySelectorAll('.chart-container');
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '50px'
        });
        
        chartContainers.forEach(container => {
            observer.observe(container);
        });
        
        // 为每个图表添加展开事件监听
        chartContainers.forEach(container => {
            container.addEventListener('toggle', function() {
                if (this.open) {
                    // 图表展开时，触发Plotly的自适应调整
                    setTimeout(() => {
                        const plotlyDiv = this.querySelector('.plotly-graph-div');
                        if (plotlyDiv && window.Plotly) {
                            window.Plotly.Plots.resize(plotlyDiv);
                        }
                    }, 100);
                }
            });
        });
    });
    </script>
    <button class="expand-all-charts" onclick="toggleAllCharts()">📊 展开所有图表</button>
    """


def generate_chart_for_single_indicator(
    function_id: str,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lookback_days: int = 365
) -> str:
    """
    为单个指标生成图表（简化接口，供 main.py 调用）
    
    V6.0增强：支持复杂技术指标（MACD、OBV、Volume、Donchian）
    采用适配器模式，实时计算技术指标
    
    参数:
        function_id: 指标的function_id（如 "get_vix"）
        cache_dir: 缓存目录
        lookback_days: 回溯天数
    
    返回:
        图表HTML字符串，如果失败返回空字符串
    """
    if function_id not in CHART_INDICATORS:
        return ""
    
    try:
        cache_key, chart_type, display_name = CHART_INDICATORS[function_id]
        
        # V7.0新增：多尺度MA分析使用K线图
        if function_id == "get_multi_scale_ma_position":
            try:
                # 直接从yfinance获取OHLCV数据
                if not YF_AVAILABLE:
                    logging.warning("yfinance未安装，无法生成K线图")
                    return ""
                
                from datetime import datetime, timedelta
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=lookback_days)
                
                # 下载QQQ数据
                df = yf.download('QQQ', start=start_date, end=end_date, interval="1d", progress=False, auto_adjust=False)
                
                if df.empty:
                    logging.warning("无法获取QQQ数据")
                    return ""
                
                # 标准化列名（yfinance返回的列名可能是多级索引）
                df = df.reset_index()
                
                # 处理多级列名
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
                
                # 统一转为小写
                df.columns = [col.lower() if isinstance(col, str) else col for col in df.columns]
                
                # 确保有必需的列
                required_cols = ['date', 'open', 'high', 'low', 'close']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    logging.warning(f"数据缺少必需列: {missing_cols}, 现有列: {list(df.columns)}")
                    return ""
                
                # 生成K线+MA图表
                return generate_candlestick_with_ma_chart(
                    indicator_name=display_name,
                    df=df,
                    ma_periods=[5, 20, 60, 200]
                )
                
            except Exception as e:
                logging.warning(f"生成K线图失败 ({function_id}): {str(e)}")
                import traceback
                traceback.print_exc()
                return ""
        
        # V6.0新增：检查是否为复杂技术指标，使用适配器实时计算
        v6_indicators = ["get_macd_qqq", "get_obv_qqq", "get_volume_analysis_qqq", "get_donchian_channels_qqq"]
        
        if function_id in v6_indicators:
            # 使用V6.0适配器获取实时计算的数据
            try:
                try:
                    from .chart_adapter_v6 import get_chart_data_for_v6_indicator
                except ImportError:
                    from chart_adapter_v6 import get_chart_data_for_v6_indicator
                df = get_chart_data_for_v6_indicator(function_id, lookback_days)
                
                if df is None or df.empty:
                    logging.debug(f"V6.0适配器返回空数据: {function_id}")
                    return ""
                
                # 根据图表类型调用对应的专用生成函数
                if chart_type == "macd_chart":
                    return generate_macd_chart(display_name, df)
                elif chart_type == "volume_chart":
                    return generate_volume_chart(display_name, df)
                elif chart_type == "donchian_chart":
                    return generate_donchian_chart(display_name, df)
                elif chart_type == "line_with_ma":
                    # OBV使用标准线图+均线
                    # 需要将 'obv' 列重命名为 'value' 以适配标准图表函数
                    if 'obv' in df.columns:
                        df_adapted = df[['date', 'obv']].rename(columns={'obv': 'value'})
                    else:
                        df_adapted = df[['date', 'value']]
                    percentiles = calculate_percentiles_from_data(df_adapted)
                    return generate_chart_html(
                        indicator_name=display_name,
                        df=df_adapted,
                        chart_type="line",
                        show_ma=True,
                        show_percentiles=True,
                        percentile_data=percentiles
                    )
                else:
                    logging.warning(f"未知的V6.0图表类型: {chart_type}")
                    return ""
                    
            except ImportError:
                logging.warning(f"V6.0图表适配器未安装，跳过 {function_id}")
                return ""
            except Exception as e:
                logging.warning(f"V6.0图表生成失败 ({function_id}): {str(e)}")
                return ""
        
        # 原有逻辑：从缓存读取数据
        df = get_historical_data_from_cache(cache_key, cache_dir, lookback_days)
        
        if df is None or df.empty:
            logging.debug(f"跳过图表生成 ({display_name}): 无历史数据")
            return ""
        
        # 计算百分位
        percentiles = calculate_percentiles_from_data(df)
        
        # 生成图表
        chart_html = generate_chart_html(
            indicator_name=display_name,
            df=df,
            chart_type=chart_type,
            show_ma=True,
            show_percentiles=True,
            percentile_data=percentiles
        )
        
        return chart_html
        
    except Exception as e:
        logging.warning(f"生成图表失败 ({function_id}): {str(e)}")
        return ""


# =====================================================
# 测试入口
# =====================================================

if __name__ == "__main__":
    import sys
    import io
    
    # 设置UTF-8输出
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    print("=" * 70)
    print("NDX Agent · 图表生成模块测试")
    print("=" * 70)
    
    # 检查Plotly
    if PLOTLY_AVAILABLE:
        print("[OK] Plotly 已安装")
    else:
        print("[FAIL] Plotly 未安装，请运行: pip install plotly")
        exit(1)
    
    # 测试1: 生成单个图表
    print("\n[测试1] 生成测试图表...")
    test_df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=365, freq='D'),
        'value': np.random.randn(365).cumsum() + 100
    })
    
    chart_html = generate_chart_html(
        indicator_name="测试指标",
        df=test_df,
        show_ma=True,
        show_percentiles=True,
        percentile_data={'p10': 95, 'p90': 105}
    )
    
    if chart_html and len(chart_html) > 100:
        print("[OK] 图表生成成功")
        
        # 保存测试HTML
        test_file = Path("test_chart.html")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>图表测试</title>
                {CHART_CSS}
            </head>
            <body>
                <h1>图表生成测试</h1>
                {chart_html}
            </body>
            </html>
            """)
        print(f"[OK] 测试文件已保存: {test_file}")
    else:
        print("[FAIL] 图表生成失败")
    
    # 测试2: 从缓存读取数据
    print("\n[测试2] 测试缓存读取...")
    cache_dir = DEFAULT_CACHE_DIR
    if cache_dir.exists():
        df = get_historical_data_from_cache("VIX", cache_dir, lookback_days=365)
        if df is not None:
            print(f"[OK] 成功读取VIX缓存: {len(df)} 条记录")
            
            # 测试3: 为VIX生成真实图表
            print("\n[测试3] 为VIX生成真实图表...")
            percentiles = calculate_percentiles_from_data(df)
            vix_chart = generate_chart_html(
                indicator_name="VIX恐慌指数",
                df=df,
                show_ma=True,
                show_percentiles=True,
                percentile_data=percentiles
            )
            
            if vix_chart:
                vix_file = Path("test_vix_chart.html")
                with open(vix_file, 'w', encoding='utf-8') as f:
                    f.write(f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>VIX图表测试</title>
                        {CHART_CSS}
                    </head>
                    <body>
                        <h1>VIX恐慌指数历史趋势</h1>
                        {get_expand_all_button_script()}
                        {vix_chart}
                    </body>
                    </html>
                    """)
                print(f"[OK] VIX图表已保存: {vix_file}")
        else:
            print("[WARN] VIX缓存不存在或格式错误")
    else:
        print(f"[WARN] 缓存目录不存在: {cache_dir}")
    
    print("\n" + "=" * 70)


# =====================================================
# V7.0 新增：K线+多尺度MA图表生成器
# =====================================================

def generate_candlestick_with_ma_chart(
    indicator_name: str,
    df: pd.DataFrame,
    ma_periods: List[int] = [5, 20, 60, 200]
) -> str:
    """
    生成K线图+多尺度移动平均线图表（专业级可视化）
    
    参考标准：TradingView / Bloomberg Terminal
    
    特性：
    - K线图（OHLC）
    - 多条MA线（不同颜色）
    - 当前价格标注
    - 交互式缩放、悬停提示
    - 响应式设计
    
    参数:
        indicator_name: 指标名称（如"QQQ多尺度MA分析"）
        df: 包含 ['date', 'open', 'high', 'low', 'close', 'volume'] 的DataFrame
        ma_periods: MA周期列表，默认 [5, 20, 60, 200]
    
    返回:
        HTML字符串（包含<details>标签）
    """
    if not PLOTLY_AVAILABLE:
        return f"""
        <div class="chart-container" style="padding: 16px;">
            <p style="color: #d32f2f;">⚠️ 图表功能不可用：Plotly未安装</p>
            <p style="font-size: 12px; color: #666;">请运行: pip install plotly</p>
        </div>
        """
    
    if df is None or df.empty:
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name}</summary>
            <div class="chart-content">
                <p style="color: #ff9800;">⚠️ 暂无历史数据</p>
            </div>
        </details>
        """
    
    try:
        # 确保date列是datetime类型
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 检查必需列
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"缺少必需列，需要: {required_cols}")
        
        # 创建子图（主图+成交量子图）
        from plotly.subplots import make_subplots
        
        has_volume = 'volume' in df.columns and df['volume'].notna().any()
        
        if has_volume:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.7, 0.3],
                subplot_titles=('价格与移动平均线', '成交量')
            )
        else:
            fig = make_subplots(rows=1, cols=1)
        
        # 1. 添加K线图
        fig.add_trace(
            go.Candlestick(
                x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='QQQ',
                increasing_line_color='#26a69a',  # 涨：青绿色
                decreasing_line_color='#ef5350',  # 跌：红色
                increasing_fillcolor='#26a69a',
                decreasing_fillcolor='#ef5350',
                hovertext=df['date'].dt.strftime('%Y-%m-%d'),
                hoverinfo='text+y'
            ),
            row=1, col=1
        )
        
        # 2. 添加多条MA线（专业配色）
        ma_colors = {
            5: '#FFD700',    # 金色（超短期）
            20: '#4169E1',   # 皇家蓝（短期）
            60: '#9370DB',   # 中紫色（中期）
            200: '#808080'   # 灰色（长期）
        }
        
        ma_labels = {
            5: 'MA5 (1周)',
            20: 'MA20 (1月)',
            60: 'MA60 (1季)',
            200: 'MA200 (1年)'
        }
        
        for period in ma_periods:
            if len(df) >= period:
                ma_values = df['close'].rolling(window=period, min_periods=period).mean()
                
                fig.add_trace(
                    go.Scatter(
                        x=df['date'],
                        y=ma_values,
                        mode='lines',
                        name=ma_labels.get(period, f'MA{period}'),
                        line=dict(
                            color=ma_colors.get(period, '#999999'),
                            width=2 if period <= 20 else 2.5,
                            shape='spline'
                        ),
                        hovertemplate=f'<b>%{{x|%Y-%m-%d}}</b><br>MA{period}: $%{{y:.2f}}<extra></extra>'
                    ),
                    row=1, col=1
                )
        
        # 3. 添加成交量柱状图（如果有数据）
        if has_volume:
            # 根据涨跌着色
            colors = ['#26a69a' if close >= open else '#ef5350' 
                     for close, open in zip(df['close'], df['open'])]
            
            fig.add_trace(
                go.Bar(
                    x=df['date'],
                    y=df['volume'],
                    name='成交量',
                    marker_color=colors,
                    opacity=0.7,
                    hovertemplate='<b>%{x|%Y-%m-%d}</b><br>成交量: %{y:,.0f}<extra></extra>'
                ),
                row=2, col=1
            )
        
        # 4. 布局设置（专业级）
        fig.update_layout(
            title=dict(
                text=f"<b>{indicator_name}</b>",
                font=dict(
                    size=20,
                    color=CHART_CONFIG['colors']['text'],
                    family=CHART_CONFIG['fonts']['title']
                ),
                x=0.02,
                xanchor='left'
            ),
            xaxis=dict(
                rangeslider=dict(visible=False),  # 禁用范围滑块
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                showline=True,
                linewidth=1,
                linecolor='#e0e0e0'
            ),
            yaxis=dict(
                title="价格 (USD)",
                showgrid=True,
                gridcolor=CHART_CONFIG['colors']['grid'],
                side='right'  # Y轴放右侧（专业软件标准）
            ),
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor="white",
                font_size=13,
                font_family=CHART_CONFIG['fonts']['body'],
                bordercolor=CHART_CONFIG['colors']['primary']
            ),
            template=CHART_CONFIG['template'],
            height=600 if has_volume else 500,
            margin=dict(l=20, r=60, t=70, b=50),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor=CHART_CONFIG['colors']['grid'],
                borderwidth=1,
                font=dict(
                    size=12,
                    color=CHART_CONFIG['colors']['text']
                )
            ),
            plot_bgcolor='rgba(250,251,252,0.5)',
            paper_bgcolor='white',
            font=dict(
                family=CHART_CONFIG['fonts']['body'],
                color=CHART_CONFIG['colors']['text']
            )
        )
        
        # 成交量子图Y轴设置
        if has_volume:
            fig.update_yaxes(
                title="成交量",
                showgrid=False,
                row=2, col=1
            )
        
        # 转换为HTML
        chart_html = fig.to_html(
            include_plotlyjs='cdn',
            div_id=f"chart_candlestick_{indicator_name.replace(' ', '_').replace('/', '_')}",
            config={
                'displayModeBar': True,
                'displaylogo': False,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'{indicator_name}_candlestick',
                    'height': 1000,
                    'width': 1600,
                    'scale': 2
                },
                'responsive': True,
                'scrollZoom': True,
            }
        )
        
        # 生成元数据
        latest = df.iloc[-1]
        latest_date = latest['date'].strftime('%Y-%m-%d')
        latest_close = latest['close']
        latest_open = latest['open']
        latest_high = latest['high']
        latest_low = latest['low']
        
        # 计算日变化
        change = latest_close - latest_open
        change_pct = (change / latest_open) * 100
        
        # 计算相对于各MA的位置
        ma_positions = {}
        for period in ma_periods:
            if len(df) >= period:
                ma_value = df['close'].rolling(window=period).mean().iloc[-1]
                if pd.notna(ma_value):
                    deviation_pct = ((latest_close - ma_value) / ma_value) * 100
                    ma_positions[period] = {
                        'value': ma_value,
                        'deviation_pct': deviation_pct
                    }
        
        # 生成MA位置描述
        ma_position_html = ""
        for period in ma_periods:
            if period in ma_positions:
                ma_val = ma_positions[period]['value']
                dev_pct = ma_positions[period]['deviation_pct']
                color = ma_colors.get(period, '#999999')
                
                # 判断位置
                if dev_pct > 0:
                    position_text = f"上方 +{dev_pct:.2f}%"
                    icon = "📈"
                else:
                    position_text = f"下方 {dev_pct:.2f}%"
                    icon = "📉"
                
                ma_position_html += f"""
                <div class="chart-meta-item">
                    <span class="chart-meta-label" style="color: {color};">●</span>
                    <span class="chart-meta-label">MA{period}:</span>
                    <span class="chart-meta-value">${ma_val:.2f} ({icon} {position_text})</span>
                </div>
                """
        
        # 成交量信息
        volume_html = ""
        if has_volume:
            latest_volume = latest['volume']
            if len(df) >= 20:
                avg_volume = df['volume'].tail(20).mean()
                volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 1
                volume_html = f"""
                <div class="chart-meta-item">
                    <span class="chart-meta-label">成交量:</span>
                    <span class="chart-meta-value">{latest_volume:,.0f} ({volume_ratio:.2f}x 20日均量)</span>
                </div>
                """
        
        meta_html = f"""
        <div class="chart-meta">
            <div class="chart-meta-item">
                <span class="chart-meta-label">日期:</span>
                <span class="chart-meta-value">{latest_date}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">收盘:</span>
                <span class="chart-meta-value">${latest_close:.2f}</span>
                <span class="trend-indicator {'trend-up' if change >= 0 else 'trend-down'}">
                    {'📈' if change >= 0 else '📉'} {change_pct:+.2f}%
                </span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">开盘:</span>
                <span class="chart-meta-value">${latest_open:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">最高:</span>
                <span class="chart-meta-value">${latest_high:.2f}</span>
            </div>
            <div class="chart-meta-item">
                <span class="chart-meta-label">最低:</span>
                <span class="chart-meta-value">${latest_low:.2f}</span>
            </div>
            {volume_html}
        </div>
        
        <div class="chart-meta" style="margin-top: 12px;">
            <div style="width: 100%; margin-bottom: 8px;">
                <span class="chart-meta-label" style="font-size: 14px; font-weight: 700;">价格相对于各MA的位置：</span>
            </div>
            {ma_position_html}
        </div>
        """
        
        # 包装在<details>标签中
        collapsible_html = f"""
        <details class="chart-container" open>
            <summary class="chart-title">{indicator_name}</summary>
            <div class="chart-content">
                {chart_html}
                {meta_html}
            </div>
        </details>
        """
        
        return collapsible_html
        
    except Exception as e:
        logging.error(f"生成K线+MA图表失败 ({indicator_name}): {str(e)}")
        import traceback
        traceback.print_exc()
        return f"""
        <details class="chart-container">
            <summary class="chart-title">{indicator_name}</summary>
            <div class="chart-content">
                <p style="color: #d32f2f;">❌ 图表生成失败: {str(e)}</p>
            </div>
        </details>
        """
    print("测试完成！")

