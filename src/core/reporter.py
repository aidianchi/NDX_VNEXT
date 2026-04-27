# -*- coding: utf-8 -*-
"""
core.reporter

报告生成器

负责根据AI分析结果生成HTML报告，包括：
- 五层分析全景
- 交互式图表
- 推理链可视化
- 新闻情报整合
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# 导入配置
try:
    from ..config import path_config
except ImportError:
    from config import path_config

class ReportGenerator:
    """根据V9框架的叙事驱动型logic_json生成最终的HTML报告。"""
    
    def __init__(self, use_charts: bool = True):
        """
        初始化报告生成器
        
        参数:
            use_charts: 是否生成交互式图表（默认True）
        """
        self.use_charts = use_charts
        
        # 尝试导入图表生成器
        if self.use_charts:
            try:
                try:
                    from ..chart_generator import generate_chart_for_single_indicator, generate_overlay_chart_for_indicator, CHART_INDICATORS, CHART_CSS
                except ImportError:
                    from chart_generator import generate_chart_for_single_indicator, generate_overlay_chart_for_indicator, CHART_INDICATORS, CHART_CSS
                self.generate_chart = generate_chart_for_single_indicator
                self.generate_overlay_chart = generate_overlay_chart_for_indicator
                self.chart_indicators = CHART_INDICATORS
                self.chart_css = CHART_CSS
                logging.info("图表生成功能已启用")
            except ImportError as e:
                logging.warning(f"无法导入图表生成器，图表功能将被禁用: {e}")
                self.use_charts = False
    
    def _find_narrative(self, indicator: Dict, narrative_map: Dict) -> str:
        """
        智能匹配指标与AI生成的叙事文本。
        支持多种匹配策略：精确匹配 -> 部分匹配 -> function_id映射 -> series_id匹配
        """
        metric_name = indicator.get('metric_name', '')
        raw_data = indicator.get('raw_data', {})
        series_id = raw_data.get('series_id', '')
        function_id = indicator.get('function_id', '')
        
        # 策略1: 精确匹配 metric_name
        if metric_name in narrative_map:
            return narrative_map[metric_name]
        
        # 策略2: 精确匹配 series_id
        if series_id in narrative_map:
            return narrative_map[series_id]
        
        # 策略3: 部分匹配 - 检查AI生成的metric是否包含在metric_name中，或反之
        for ai_metric, narrative in narrative_map.items():
            # 移除常见后缀和括号内容，进行核心关键词匹配
            ai_metric_clean = ai_metric.lower().replace('(', '').replace(')', '').strip()
            metric_name_clean = metric_name.lower().replace('(', '').replace(')', '').strip()
            
            # 提取核心关键词（去除常见修饰词）
            ai_keywords = set([w for w in ai_metric_clean.split() if len(w) > 2 and w not in ['the', 'and', 'for', 'with']])
            name_keywords = set([w for w in metric_name_clean.split() if len(w) > 2 and w not in ['the', 'and', 'for', 'with']])
            
            # 如果核心关键词有重叠，认为匹配
            if ai_keywords and name_keywords and (ai_keywords & name_keywords):
                # 进一步验证：至少50%的关键词匹配
                overlap_ratio = len(ai_keywords & name_keywords) / max(len(ai_keywords), len(name_keywords))
                if overlap_ratio >= 0.5:
                    logging.debug(f"部分匹配成功: '{metric_name}' <-> '{ai_metric}' (重叠率: {overlap_ratio:.2f})")
                    return narrative
        
        # 策略4: 通过function_id建立映射表（特殊情况的硬编码映射）
        function_to_metric_map = {
            'get_net_liquidity_momentum': ['Net Liquidity', 'Net Liquidity Momentum'],
            'get_crowdedness_dashboard': ['Crowdedness', 'Put/Call', 'Put Call'],
            'get_advance_decline_line': ['Advance/Decline', 'Advance Decline', 'A/D Line'],
            'get_fed_funds_rate': ['Fed Funds', 'Federal Funds'],
            'get_m2_yoy': ['M2', 'M2 YoY'],
            'get_10y_treasury': ['10Y Treasury', '10Y Yield', '10 Year Treasury'],
            'get_10y_breakeven': ['Breakeven', '10Y Breakeven'],
            'get_vix': ['VIX'],
            'get_vxn': ['VXN'],
            'get_hy_oas_bp': ['High Yield OAS', 'HY OAS'],
            'get_hyg_momentum': ['HYG', 'High Yield Corp'],
            'get_vxn_vix_ratio': ['VXN/VIX', 'VXN VIX'],
            'get_percent_above_ma': ['Percent Above', 'Stocks Above MA', '% Above'],
            'get_m7_fundamentals': ['M7', 'M7 Fundamentals'],
            'get_new_highs_lows': ['New Highs', 'New Lows', 'Highs-Lows'],
            'get_mcclellan_oscillator_nasdaq_or_nyse': ['McClellan', 'Oscillator'],
            'get_ndx_pe_and_earnings_yield': ['NDX Valuation', 'NDX PE', 'PB'],
            'get_equity_risk_premium': ['Equity Risk Premium', 'ERP'],
            'get_qqq_technical_indicators': ['QQQ Technical', 'Technical Indicators'],
            'get_rsi_qqq': ['RSI'],
            'get_atr_qqq': ['ATR'],
            'get_adx_qqq': ['ADX'],
        }
        
        if function_id in function_to_metric_map:
            for keyword in function_to_metric_map[function_id]:
                for ai_metric, narrative in narrative_map.items():
                    if keyword.lower() in ai_metric.lower():
                        logging.debug(f"通过function_id映射匹配: '{function_id}' -> '{ai_metric}'")
                        return narrative
        
        # 策略5: 最后尝试 - 模糊匹配（包含关系）
        metric_name_lower = metric_name.lower()
        for ai_metric, narrative in narrative_map.items():
            ai_metric_lower = ai_metric.lower()
            # 如果metric_name包含AI metric的核心部分，或反之
            if (len(ai_metric_lower) > 5 and ai_metric_lower in metric_name_lower) or \
               (len(metric_name_lower) > 5 and metric_name_lower in ai_metric_lower):
                logging.debug(f"模糊匹配成功: '{metric_name}' <-> '{ai_metric}'")
                return narrative
        
        return 'AI未提供叙事。'

    def _generate_chart_html(self, indicator: Dict) -> str:
        """
        为单个指标生成图表HTML
        
        参数:
            indicator: 指标数据字典
            
        返回:
            图表HTML字符串，如果无法生成则返回空字符串
        """
        if not self.use_charts:
            return ""
        
        function_id = indicator.get('function_id', '')
        
        # 检查该指标是否需要生成图表
        if function_id not in self.chart_indicators:
            return ""
        
        try:
            # 调用图表生成器（使用10年历史数据，与分析层保持一致）
            chart_html = self.generate_chart(function_id, lookback_days=3650)
            if chart_html:
                logging.info(f"  ✔ 已为 {function_id} 生成图表 (10年数据)")
                overlay_html = ""
                if hasattr(self, "generate_overlay_chart"):
                    overlay_html = self.generate_overlay_chart(function_id, lookback_days=3650)
                return f"{chart_html}{overlay_html}"
            else:
                logging.debug(f"  - {function_id} 图表生成返回空")
                return ""
        except Exception as e:
            logging.warning(f"  ! 生成 {function_id} 图表时出错: {str(e)[:100]}")
            return ""

    def _generate_layer_html(self, layer_num: int, layer_conclusion: Dict, data_json: Dict, logic_json: Dict) -> str:
        # 1. 从AI的分析结果中，创建一个易于查询的 "指标名称 -> 叙事文本" 的映射
        narrative_map = {
            item.get('metric', ''): item.get('narrative', 'N/A')
            for item in logic_json.get('indicator_narratives', {}).get(f"layer_{layer_num}", [])
        }
        
        # 【新增】创建 "指标名称 -> 推理过程" 的映射
        reasoning_map = {
            item.get('metric', ''): item.get('reasoning_process', '')
            for item in logic_json.get('indicator_narratives', {}).get(f"layer_{layer_num}", [])
        }

        # 2. 从原始数据中筛选出当前层级的所有指标
        layer_indicators = [ind for ind in data_json.get('indicators', []) if ind.get('layer') == layer_num]

        # 3. 构建每个指标的HTML，并附加上带时间戳的Tooltip、图表和推理过程
        narratives_html = ""
        for indicator in layer_indicators:
            metric_name = indicator.get('metric_name', '未知指标')
            # 使用智能匹配函数查找对应的叙事文本
            narrative_text = self._find_narrative(indicator, narrative_map)
            timestamp = indicator.get('collection_timestamp_utc', 'N/A')

            # 创建一个带下划虚线的span，鼠标悬浮时显示完整的时间戳
            metric_html_with_tooltip = f'<span style="border-bottom: 1px dotted #000; cursor: help;" title="数据收集于: {timestamp}Z">{metric_name}</span>'

            # 生成图表HTML（如果适用）
            chart_html = self._generate_chart_html(indicator)
            
            # 【新增】生成推理过程HTML
            reasoning_process = reasoning_map.get(metric_name, '')
            reasoning_html = self._generate_reasoning_process_html(reasoning_process)

            narratives_html += f"""
                <div class="narrative-item">
                    <div class="narrative-metric">{metric_html_with_tooltip}</div>
                    <div class="narrative-text">{narrative_text}</div>
                    {chart_html}
                    {reasoning_html}
                </div>
            """

        # 4. 组装整个层级的HTML（这部分与旧代码类似）
        key_drivers_html = "".join([f'<span class="driver-chip">{driver}</span>' for driver in layer_conclusion.get("key_drivers", [])])
        return f"""
            <div class="layer-card">
                <div class="layer-header"><h3>{layer_conclusion.get('layer', '未知')}</h3></div>
                <div class="layer-section"><h4>定性判断</h4><p class="judgement">{layer_conclusion.get('judgement', 'N/A')}</p></div>
                <div class="layer-section conflict-section"><h4>内部矛盾</h4><p>{layer_conclusion.get('internal_conflict_analysis', '无')}</p></div>
                <div class="layer-section"><h4>关键驱动</h4><div class="drivers-container">{key_drivers_html}</div></div>
                <details class="narrative-toggle"><summary>展开指标级叙事</summary><div class="narrative-content">{narratives_html if narratives_html else '<p>无</p>'}</div></details>
            </div>
        """

    def _generate_revision_summary_html(self, revision_summary: Dict) -> str:
        if not revision_summary: return ""
        items_html = "".join([f"<li><strong>{key.replace('_', ' ').title()}:</strong> {value}</li>" for key, value in revision_summary.items()])
        return f"""<div class="panel"><details><summary style="font-size: 1.5rem; font-weight: 600; cursor: pointer;">AI自我修订摘要</summary><div class="revision-summary-content"><ul>{items_html}</ul></div></details></div>"""

    def _generate_reasoning_process_html(self, reasoning_process: str) -> str:
        """
        生成推理过程HTML（自由文本版）
        
        Args:
            reasoning_process: AI的推理过程文本
            
        Returns:
            推理过程的HTML字符串，如果为空则返回空字符串
        """
        if not reasoning_process or reasoning_process.strip() == "":
            return ""
        
        # 转义HTML特殊字符，保留换行
        import html
        escaped_text = html.escape(reasoning_process)
        
        return f"""
        <details class="reasoning-toggle">
            <summary>💭 查看AI的推理过程</summary>
            <div class="reasoning-content">
                <p>{escaped_text}</p>
            </div>
        </details>
        """

    def _generate_reasoning_chain_html(self, logic_json: Dict) -> str:
        """
        生成推理链可视化HTML（非侵入式方案A）
        从现有的三阶段输出中提取推理过程，无需修改AI提示词
        """
        actual_logic = logic_json.get('__LOGIC__', logic_json)
        
        # 检查是否存在revision_summary（标志着完整的三阶段流程）
        has_full_chain = bool(actual_logic.get('revision_summary'))
        
        if not has_full_chain:
            # 如果没有完整流程，不显示推理链
            return ""
        
        # 阶段1：Analyst（分析初稿）- 从indicator_narratives提取
        stage1_content = ""
        indicator_narratives = actual_logic.get('indicator_narratives', {})
        if indicator_narratives:
            stage1_content = "<h4>指标级叙事生成</h4>"
            for layer_key in ['layer_1', 'layer_2', 'layer_3', 'layer_4', 'layer_5']:
                layer_items = indicator_narratives.get(layer_key, [])
                if layer_items:
                    stage1_content += f"<p><strong>{layer_key.replace('_', ' ').title()}:</strong> 生成了 {len(layer_items)} 个指标叙事</p>"
        
        # 阶段2：Critic（批评意见）- 从revision_summary反推
        stage2_content = "<h4>质询与批评</h4>"
        revision_summary = actual_logic.get('revision_summary', {})
        critique_count = len(revision_summary)
        stage2_content += f"<p>对初稿提出了 <strong>{critique_count}</strong> 条批评意见，涵盖：</p><ul>"
        
        critique_types = {'采纳': 0, '部分采纳': 0, '驳回': 0}
        for key, value in revision_summary.items():
            if '【采纳】' in value:
                critique_types['采纳'] += 1
            elif '【部分采纳】' in value:
                critique_types['部分采纳'] += 1
            elif '【驳回】' in value:
                critique_types['驳回'] += 1
        
        for ctype, count in critique_types.items():
            if count > 0:
                stage2_content += f"<li>{ctype}: {count} 条</li>"
        stage2_content += "</ul>"
        
        # 阶段3：Reviser（修订终稿）- 从revision_summary提取
        stage3_content = "<h4>修订与整合</h4>"
        stage3_content += "<p>基于批评意见，对初稿进行了以下修订：</p><ul>"
        for key, value in list(revision_summary.items())[:3]:  # 显示前3条
            short_key = key.replace('response_to_critique_', '批评意见 #')
            stage3_content += f"<li><strong>{short_key}:</strong> {value[:100]}...</li>"
        if len(revision_summary) > 3:
            stage3_content += f"<li><em>...以及其他 {len(revision_summary) - 3} 条修订</em></li>"
        stage3_content += "</ul>"
        
        # 组装完整的推理链HTML
        return f"""
        <div class="panel reasoning-chain-panel">
            <details class="reasoning-chain-toggle">
                <summary style="font-size: 1.5rem; font-weight: 600; cursor: pointer;">
                    🧠 AI推理链可视化 (Analyst → Critic → Reviser)
                </summary>
                <div class="reasoning-chain-content">
                    <div class="reasoning-stage">
                        <div class="stage-header stage-1">
                            <span class="stage-number">阶段 1</span>
                            <span class="stage-name">Analyst (分析初稿)</span>
                        </div>
                        <div class="stage-body">
                            {stage1_content}
                        </div>
                    </div>
                    
                    <div class="reasoning-arrow">↓</div>
                    
                    <div class="reasoning-stage">
                        <div class="stage-header stage-2">
                            <span class="stage-number">阶段 2</span>
                            <span class="stage-name">Critic (批判性审查)</span>
                        </div>
                        <div class="stage-body">
                            {stage2_content}
                        </div>
                    </div>
                    
                    <div class="reasoning-arrow">↓</div>
                    
                    <div class="reasoning-stage">
                        <div class="stage-header stage-3">
                            <span class="stage-number">阶段 3</span>
                            <span class="stage-name">Reviser (修订终稿)</span>
                        </div>
                        <div class="stage-body">
                            {stage3_content}
                        </div>
                    </div>
                    
                    <div class="reasoning-summary">
                        <p><strong>推理链完整性:</strong> ✓ 已完成三阶段交叉问询流程</p>
                        <p><strong>质量保证:</strong> 通过 Critic 阶段的 {critique_count} 条质询，确保分析逻辑的严密性</p>
                    </div>
                </div>
            </details>
        </div>
        """

    def _generate_news_intelligence_html(self, data_json: Dict) -> str:
        """
        生成新闻情报模块的HTML
        
        Args:
            data_json: 包含news_intelligence的数据JSON
            
        Returns:
            新闻模块HTML字符串
        """
        news_intel = data_json.get('news_intelligence')
        
        if not news_intel or not news_intel.get('enabled'):
            return ""
        
        # 构建新闻HTML
        news_html = f"""
        <div class="panel">
            <h2>📰 新闻情报 (News Intelligence)</h2>
            <div style="text-align: center; color: #718096; margin-bottom: 1.5rem;">
                <span>总计 {news_intel.get('total_items', 0)} 条新闻</span> | 
                <span>更新时间: {news_intel.get('last_update', 'N/A')}</span>
            </div>
        """
        
        # 按层级展示新闻
        for layer, info in news_intel.get('by_layer', {}).items():
            sentiment = info.get('avg_sentiment', 0.0)
            sentiment_color = '#48bb78' if sentiment > 0.2 else ('#e53e3e' if sentiment < -0.2 else '#718096')
            sentiment_icon = '📈' if sentiment > 0.2 else ('📉' if sentiment < -0.2 else '➡️')
            
            news_html += f"""
            <div class="news-layer-card">
                <div class="news-layer-header">
                    <h3>{layer}</h3>
                    <span class="news-sentiment" style="color: {sentiment_color};">
                        {sentiment_icon} 情绪: {sentiment:.2f}
                    </span>
                </div>
                <div class="news-summary">{info.get('summary', '')}</div>
                <details class="news-toggle">
                    <summary>查看 {info.get('count', 0)} 条新闻标题</summary>
                    <div class="news-items">
            """
            
            # 显示新闻条目
            for item in info.get('items', [])[:10]:  # 最多显示10条
                item_sentiment = item.get('sentiment', 0.0)
                sentiment_badge = '🟢' if item_sentiment > 0.2 else ('🔴' if item_sentiment < -0.2 else '⚪')
                
                news_html += f"""
                <div class="news-item">
                    <div class="news-item-header">
                        <span class="news-sentiment-badge">{sentiment_badge}</span>
                        <a href="{item.get('url', '#')}" target="_blank" class="news-title">
                            {item.get('title', '无标题')}
                        </a>
                    </div>
                    <div class="news-meta">
                        <span>来源: {item.get('source', 'Unknown')}</span> | 
                        <span>发布: {item.get('published_date', 'N/A')[:10]}</span>
                        {' | 关键词: ' + ', '.join(item.get('keywords', [])[:3]) if item.get('keywords') else ''}
                    </div>
                </div>
                """
            
            news_html += """
                    </div>
                </details>
            </div>
            """
        
        news_html += "</div>"
        return news_html

    def _generate_html_report(self, logic_json: Dict, data_json: Dict, backtest_date: Optional[str]) -> str:
        # 处理可能的 __LOGIC__ 嵌套结构
        actual_logic = logic_json.get('__LOGIC__', logic_json)
        
        regime_analysis = actual_logic.get('market_regime_analysis', {})
        integrity_report = actual_logic.get('data_integrity_report', {})
        revision_summary = actual_logic.get('revision_summary', {})
        revision_summary_html = self._generate_revision_summary_html(revision_summary)
        masters_perspective_text = actual_logic.get('masters_perspective')
        if not masters_perspective_text:
            masters_perspective_text = regime_analysis.get('masters_perspective', 'N/A')
        
        # 构造各层HTML（现在包含图表）
        logging.info("\n[报告生成] 开始生成各层级HTML内容...")
        layers_html = ""
        if 'layer_conclusions' in actual_logic and 'indicator_narratives' in actual_logic:
            for i, c in enumerate(actual_logic['layer_conclusions']):
                layer_num = i + 1
                logging.info(f"  - 正在生成第{layer_num}层内容...")
                layers_html += self._generate_layer_html(layer_num, c, data_json, actual_logic)

        # risk_flags 可能在 market_regime_analysis 中，也可能在顶层
        risk_flags = regime_analysis.get('risk_flags', []) or actual_logic.get('risk_flags', [])
        risk_flags_html = "".join([f'<li class="risk-flag">{flag}</li>' for flag in risk_flags])
        
        report_title = f"NDX Command V9 Report - {backtest_date}" if backtest_date else f"NDX Command V9 Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subtitle = f"历史时点分析: {backtest_date}" if backtest_date else f"实时分析报告 · {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        # 获取图表CSS（如果启用）
        chart_css_content = self.chart_css if self.use_charts else ""
        
        # 【新增】新闻模块CSS
        news_css = """
        .news-layer-card{background:#fdfdff;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;border:1px solid #eef2f7}
        .news-layer-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem}
        .news-layer-header h3{color:#2d3748;font-size:1.2rem;margin:0}
        .news-sentiment{font-size:0.9rem;font-weight:600}
        .news-summary{background:#f8f9fa;padding:1rem;border-radius:8px;margin-bottom:1rem;font-style:italic;color:#4a5568}
        .news-toggle summary{cursor:pointer;color:#667eea;font-weight:500;margin-top:0.5rem}
        .news-items{margin-top:1rem}
        .news-item{border-bottom:1px solid #eef2f7;padding:0.75rem 0}
        .news-item:last-child{border:none}
        .news-item-header{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem}
        .news-sentiment-badge{font-size:0.8rem}
        .news-title{color:#2d3748;text-decoration:none;font-weight:500}
        .news-title:hover{color:#667eea;text-decoration:underline}
        .news-meta{font-size:0.85rem;color:#718096}
        """
        
        # 【新增】推理链可视化CSS
        reasoning_chain_css = """
        .reasoning-chain-panel{background:linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%);border:2px solid #667eea}
        .reasoning-chain-toggle summary{color:#2d3748;padding:0.5rem}
        .reasoning-chain-content{background:#fff;border-radius:8px;padding:2rem;margin-top:1rem}
        .reasoning-stage{background:#fdfdff;border-radius:10px;padding:1.5rem;margin-bottom:1rem;border-left:4px solid #cbd5e0}
        .stage-header{display:flex;align-items:center;gap:1rem;margin-bottom:1rem;padding-bottom:0.75rem;border-bottom:2px solid #e2e8f0}
        .stage-number{background:#667eea;color:#fff;padding:0.25rem 0.75rem;border-radius:20px;font-weight:700;font-size:0.85rem}
        .stage-name{font-size:1.2rem;font-weight:600;color:#2d3748}
        .stage-1 .stage-number{background:#48bb78}
        .stage-2 .stage-number{background:#ed8936}
        .stage-3 .stage-number{background:#667eea}
        .stage-body{color:#4a5568;line-height:1.8}
        .stage-body h4{color:#2d3748;font-size:1rem;margin-top:0;margin-bottom:0.5rem}
        .stage-body ul{margin-left:1.5rem}
        .stage-body li{margin-bottom:0.5rem}
        .reasoning-arrow{text-align:center;font-size:2rem;color:#667eea;margin:0.5rem 0}
        .reasoning-summary{background:#f8f9fa;border-radius:8px;padding:1.5rem;margin-top:1.5rem;border-left:4px solid #48bb78}
        .reasoning-summary p{margin:0.5rem 0;color:#2d3748}
        """
        
        # 【新增】推理过程CSS（自由文本版）
        reasoning_process_css = """
        .reasoning-toggle{margin-top:0.75rem}
        .reasoning-toggle summary{cursor:pointer;color:#667eea;font-size:0.9rem;user-select:none;padding:0.25rem 0;transition:color 0.2s}
        .reasoning-toggle summary:hover{color:#5a67d8}
        .reasoning-toggle[open] summary{color:#5a67d8;font-weight:500}
        .reasoning-content{background:#f8f9fa;padding:1rem 1.25rem;border-radius:8px;margin-top:0.5rem;border-left:3px solid #667eea;font-style:italic;color:#4a5568;line-height:1.8;white-space:pre-wrap}
        .reasoning-content p{margin:0;text-align:justify}
        """

        return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{report_title}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;background-color:#f4f7fa;color:#333;padding:2rem;line-height:1.6}}.container{{max-width:1200px;margin:0 auto}}.header{{text-align:center;margin-bottom:2rem}}.header h1{{font-size:2.5rem;color:#2c3e50}}.header .subtitle{{font-size:1.1rem;color:#7f8c8d}}.panel{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 8px 32px rgba(0,0,0,.07);margin-bottom:2rem}}h2{{font-size:1.75rem;margin-bottom:1.5rem;color:#34495e;border-bottom:2px solid #e0e6ed;padding-bottom:.75rem}}.regime-card{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:2rem;border-radius:12px;text-align:center}}.regime-card .regime-title{{font-size:1.2rem;opacity:.8;margin-bottom:.5rem}}.regime-card .regime-name{{font-size:2rem;font-weight:700;margin-bottom:1.5rem}}.conflict-card{{background-color:#fff9f0;border:1px solid #ffeada;padding:1.5rem;border-radius:8px;margin-top:1.5rem;color:#333}}.conflict-card h4{{color:#d95f02}}.rationale{{margin-top:1rem;text-align:left;font-size:1.05rem}}.layer-card{{background:#fdfdff;border-radius:10px;padding:1.5rem;margin-bottom:1.5rem;border:1px solid #eef2f7}}.layer-header h3{{color:#2d3748;font-size:1.4rem}}.layer-section{{margin-top:1.2rem}}.layer-section h4{{color:#4a5568;font-size:1.1rem;margin-bottom:.5rem}}.judgement{{font-weight:500;font-style:italic;color:#2c3e50;background-color:#f8f9fa;padding:.75rem;border-left:4px solid #667eea;border-radius:4px}}.conflict-section p{{background-color:#fff5f5;border-left:4px solid #e53e3e;padding:.75rem;border-radius:4px}}.drivers-container{{display:flex;flex-wrap:wrap;gap:.5rem}}.driver-chip{{background-color:#e2e8f0;color:#4a5568;padding:.25rem .75rem;border-radius:16px;font-size:.85rem}}.narrative-toggle summary{{cursor:pointer;color:#667eea;font-weight:500;margin-top:1.2rem}}.narrative-content{{background-color:#f8f9fa;border-radius:8px;padding:1rem;margin-top:.5rem}}.narrative-item{{border-bottom:1px solid #eef2f7;padding:.75rem 0}}.narrative-item:last-child{{border:none}}.risk-flag{{background:#fff5f5;border-left:4px solid #e53e3e;padding:.75rem 1.25rem;margin-bottom:.75rem;color:#c53030;list-style:none;border-radius:4px}}.revision-summary-content{{background-color:#f8f9fa;border-radius:8px;padding:.1rem 1.5rem;margin-top:1rem}}.revision-summary-content ul li{{margin-bottom:.75rem}}.integrity-report{{font-size:.9rem;text-align:center;color:#718096;background-color:#eef2f7;padding:.75rem;border-radius:8px}}.footer{{text-align:center;color:#aaa;margin-top:3rem;font-size:.9rem}}{chart_css_content}{news_css}{reasoning_chain_css}{reasoning_process_css}</style></head><body><div class="container"><div class="header"><h1>NDX Command V9</h1><div class="subtitle">{subtitle}</div></div><div class="panel"><h2>最终战略研判</h2><div class="regime-card"><div class="regime-title">最终市场范式判断</div><div class="regime-name">{regime_analysis.get('identified_regime', 'N/A')}</div><div class="conflict-card"><h4>核心冲突情景: [{regime_analysis.get('identified_conflict_scenario_ID', 'N/A')}]</h4><p>{regime_analysis.get('conflict_rationale', 'N/A')}</p></div><div class="rationale"><p>{regime_analysis.get('regime_rationale', 'N/A')}</p></div></div></div>{self._generate_reasoning_chain_html(logic_json)}{revision_summary_html}{self._generate_news_intelligence_html(data_json)}<div class="panel"><h2>五层分析全景</h2>{layers_html}</div><div class="panel"><h2>关键风险与大师视角</h2><ul>{risk_flags_html if risk_flags_html else '<li>无</li>'}</ul><div style="margin-top:1.5rem; padding:1.5rem; background:#f8f9fa; border-radius:8px;"><h4>大师视角 (Masters' Perspective)</h4><p style="white-space: pre-wrap;">{masters_perspective_text}</p></div></div><div class="integrity-report"><b>数据完整性:</b> {integrity_report.get('confidence_percent', 0):.1f}% | <b>备注:</b> {integrity_report.get('notes', '无')}</div><div class="footer"><p>Generated by NDX Command Agent v9.4 (with Interactive Charts & Reasoning Process)</p></div></div></body></html>"""

    def run(self, logic_json: Dict, data_json: Dict, backtest_date: Optional[str] = None) -> str:
        logging.info("\n[步骤 4/4] 报告生成阶段")
        logging.info("=" * 35)
        
        if not logic_json or logic_json.get("error"):
            logging.error("逻辑JSON无效，无法生成报告。")
            return ""
        
        # 显示图表生成状态
        if self.use_charts:
            logging.info("  -> 图表生成功能: 已启用")
            logging.info(f"  -> 支持的图表指标数量: {len(self.chart_indicators)}")
        else:
            logging.info("  -> 图表生成功能: 已禁用")
            
        html_content = self._generate_html_report(logic_json, data_json, backtest_date)
        
        # 安全地生成文件名，防止路径注入
        if backtest_date:
            safe_date = backtest_date.replace('-', '')
            if not safe_date.isalnum():
                raise ValueError(f"无效的日期格式: {backtest_date}")
            report_filename = f"{path_config.reports_dir}/ndx_report_v9_{safe_date}.html"
            log_message = f"✅ V9历史分析报告生成成功: {report_filename}"
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_filename = f"{path_config.reports_dir}/ndx_report_v9_{timestamp}.html"
            log_message = f"✅ V9实时分析报告生成成功: {report_filename}"

        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        logging.info(log_message)
        
        if self.use_charts:
            logging.info("  -> 报告中已嵌入交互式图表")
        
        return report_filename

# =====================================================
# Class: 数据完整性检查 (DataIntegrity) - 保持不变
# =====================================================
