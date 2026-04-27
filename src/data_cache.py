# -*- coding: utf-8 -*-
"""
data_cache.py

共享数据缓存模块 - 消除重复数据下载

设计原则：
1. 线程安全：使用 threading.Lock 保护并发访问
2. 非侵入式：通过 context manager 注入，不修改现有函数签名
3. 可验证：提供缓存统计信息用于调试

使用方式：
    from data_cache import SharedDataCache
    
    # 在 collector.py 中初始化
    cache = SharedDataCache()
    
    # 在各工具函数中检查缓存
    df = cache.get_or_fetch('QQQ', lambda: yf.download('QQQ', ...))
"""

import threading
import logging
import time
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime
import pandas as pd

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False


class SharedDataCache:
    """
    线程安全的共享数据缓存
    
    核心功能：
    1. 避免同一数据源的重复下载
    2. 支持预加载（prefetch）常用数据
    3. 提供缓存命中率统计
    
    使用示例：
        cache = SharedDataCache()
        
        # 方式1：惰性加载
        df = cache.get_or_fetch('QQQ', fetch_func, 'QQQ', start=..., end=...)
        
        # 方式2：预加载
        cache.prefetch('QQQ', df)
        df = cache.get('QQQ')  # 后续调用直接返回缓存
    """
    
    def __init__(self, enabled: bool = True):
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._enabled = enabled
        self._inflight: Dict[str, threading.Event] = {}
        self._stats = {
            'hits': 0,
            'misses': 0,
            'prefetches': 0,
        }
        self._fetch_times: Dict[str, float] = {}
    
    def _make_key(self, ticker: str, start_date: Optional[str] = None, 
                  end_date: Optional[str] = None, data_type: str = 'price') -> str:
        """生成缓存键"""
        if start_date and end_date:
            return f"{data_type}:{ticker}:{start_date}:{end_date}"
        return f"{data_type}:{ticker}"
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据（不触发加载）"""
        if not self._enabled:
            return None
        
        with self._lock:
            if key in self._cache:
                self._stats['hits'] += 1
                logging.debug(f"[Cache HIT] {key}")
                return self._cache[key]
            return None
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存数据"""
        if not self._enabled:
            return
        
        with self._lock:
            self._cache[key] = value
            logging.debug(f"[Cache SET] {key}")
    
    def prefetch(self, key: str, value: Any) -> None:
        """预加载数据到缓存"""
        if not self._enabled:
            return
        
        with self._lock:
            self._cache[key] = value
            self._stats['prefetches'] += 1
            logging.info(f"[Cache PREFETCH] {key}")
    
    def get_or_fetch(self, key: str, fetch_func: Callable[[], Any]) -> Any:
        """
        获取缓存数据，若不存在则调用 fetch_func 加载
        
        Args:
            key: 缓存键
            fetch_func: 数据获取函数（无参数，返回数据）
        
        Returns:
            缓存或新获取的数据
        """
        if not self._enabled:
            return fetch_func()

        should_fetch = False
        wait_event: Optional[threading.Event] = None

        with self._lock:
            if key in self._cache:
                self._stats['hits'] += 1
                logging.debug(f"[Cache HIT] {key}")
                return self._cache[key]

            wait_event = self._inflight.get(key)
            if wait_event is None:
                wait_event = threading.Event()
                self._inflight[key] = wait_event
                self._stats['misses'] += 1
                should_fetch = True
                logging.info(f"[Cache MISS] {key} - fetching...")
            else:
                logging.info(f"[Cache WAIT] {key} - waiting for in-flight fetch")

        if not should_fetch:
            wait_event.wait()
            with self._lock:
                if key in self._cache:
                    self._stats['hits'] += 1
                    logging.debug(f"[Cache HIT-AFTER-WAIT] {key}")
                    return self._cache[key]

            logging.warning(f"[Cache MISS-AFTER-WAIT] {key} - refetching")
            return fetch_func()

        start_time = time.time()
        try:
            value = fetch_func()
            fetch_time = time.time() - start_time

            with self._lock:
                self._cache[key] = value
                self._fetch_times[key] = fetch_time

            logging.info(f"[Cache FETCH] {key} - {fetch_time:.2f}s")
            return value
        finally:
            with self._lock:
                event = self._inflight.pop(key, None)
                if event is not None:
                    event.set()
    
    def get_or_fetch_yf(self, ticker: str, start_date: str, end_date: str,
                        fetch_func: Optional[Callable] = None) -> pd.DataFrame:
        """
        专门用于 yfinance 数据的缓存方法
        
        Args:
            ticker: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            fetch_func: 可选的自定义获取函数
        
        Returns:
            DataFrame 包含 ['date', 'value'] 或原始 yfinance 数据
        """
        key = self._make_key(ticker, start_date, end_date, 'yf')
        
        def default_fetch():
            if not YF_AVAILABLE:
                return pd.DataFrame()
            try:
                df = yf.download(ticker, start=start_date, end=end_date, 
                                progress=False, auto_adjust=False)
                return df
            except Exception as e:
                logging.warning(f"yfinance download failed for {ticker}: {e}")
                return pd.DataFrame()
        
        return self.get_or_fetch(key, fetch_func or default_fetch)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total * 100) if total > 0 else 0
            
            return {
                'enabled': self._enabled,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'prefetches': self._stats['prefetches'],
                'hit_rate_pct': round(hit_rate, 2),
                'cached_keys': list(self._cache.keys()),
                'fetch_times': dict(self._fetch_times),
            }
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._fetch_times.clear()
            for event in self._inflight.values():
                event.set()
            self._inflight.clear()
            logging.info("[Cache CLEARED]")
    
    def is_cached(self, key: str) -> bool:
        """检查键是否已缓存"""
        with self._lock:
            return key in self._cache


class CacheContext:
    """
    缓存上下文管理器
    
    用于在数据收集过程中传递缓存实例
    """
    
    _instance: Optional['CacheContext'] = None
    _cache: Optional[SharedDataCache] = None
    
    @classmethod
    def initialize(cls, enabled: bool = True) -> SharedDataCache:
        """初始化全局缓存"""
        cls._cache = SharedDataCache(enabled=enabled)
        return cls._cache
    
    @classmethod
    def get_cache(cls) -> Optional[SharedDataCache]:
        """获取全局缓存实例"""
        return cls._cache
    
    @classmethod
    def clear(cls) -> None:
        """清空全局缓存"""
        if cls._cache:
            cls._cache.clear()


def get_global_cache() -> Optional[SharedDataCache]:
    """获取全局缓存实例的便捷函数"""
    return CacheContext.get_cache()


def init_global_cache(enabled: bool = True) -> SharedDataCache:
    """初始化全局缓存的便捷函数"""
    return CacheContext.initialize(enabled=enabled)
