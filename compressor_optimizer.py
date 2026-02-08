# compressor_optimizer.py
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import math

class CompressorOptimizer:
    def __init__(self):
        # 默认参数（与控制面板一致）
        self.default_params = {
            'current_capacity': 1000.0,  # 当前罐容(吨)
            'target_capacity': 1000.0,   # 目标罐容(吨)
            'single_machine_output': 285.0,  # 单机额定产量(吨/天)
            'empty_loss': 60.0,  # 预设放空量(吨/天)
            'valley_hours': 8,   # 低谷时长
            'flat_hours': 9,     # 平段时长
            'peak_hours': 7,     # 高峰时长
            'flat_min_load': 0.62,  # 平段最低负荷率
            'flat_max_load': 1.0,   # 平段最高负荷率
            'peak_min_load': 0.62,  # 高峰最低负荷率
            'peak_max_load': 1.0    # 高峰最高负荷率
        }
        
        # 转速-负荷率映射表（与Excel一致）
        self.rpm_load_map = {
            450: 0.617543859649123,
            470: 0.659649122807018,
            490: 0.694736842105263,
            510: 0.736842105263158,
            530: 0.771929824561403,
            550: 0.814035087719298,
            570: 0.856140350877193,
            590: 0.891228070175439,
            610: 0.933333333333333,
            630: 0.996491228070175
        }
        
        # 负荷率-转速映射（用于反向查找）
        self.load_rpm_map = {v: k for k, v in self.rpm_load_map.items()}
    
    def get_rpm_from_load(self, load_rate: float) -> int:
        """根据负荷率查找最接近的转速（Excel的LOOKUP函数逻辑）"""
        if load_rate <= 0.62:
            return 450
        elif load_rate >= 0.9965:
            return 630
        
        # 找到小于等于load_rate的最大负荷率对应的转速
        available_loads = sorted(self.rpm_load_map.values())
        closest_load = max([l for l in available_loads if l <= load_rate])
        
        # 获取对应的转速
        for rpm, load in self.rpm_load_map.items():
            if abs(load - closest_load) < 0.0001:
                return rpm
        
        # 四舍五入到最近的20的倍数
        rpm = self.load_rpm_map[closest_load]
        return round(rpm / 20) * 20
    
    def get_load_from_rpm(self, rpm: int) -> float:
        """根据转速获取负荷率"""
        return self.rpm_load_map.get(rpm, 0.62)
    
    def calculate_daily_output(self, mode: str, flat_load: float, peak_load: float) -> float:
        """计算每日预计产量（与Excel公式一致）"""
        # 单机模式各时段满负荷产量
        single_valley_output = 95      # 285 * 8/24
        single_flat_output = 106.875   # 285 * 9/24
        single_peak_output = 83.125    # 285 * 7/24
        
        if mode == "单机":
            # 单机模式：低谷固定满负荷，平段和高峰按负荷率计算
            valley_output = single_valley_output
            flat_output = single_flat_output * flat_load
            peak_output = single_peak_output * peak_load
            total_output = valley_output + flat_output + peak_output
        else:
            # 双机模式：产量翻倍
            valley_output = single_valley_output * 2
            flat_output = single_flat_output * 2 * flat_load
            peak_output = single_peak_output * 2 * peak_load
            total_output = valley_output + flat_output + peak_output
        
        return total_output
    
    def determine_mode(self, daily_demand: float, current_capacity: float) -> str:
        """确定运行模式（与Excel逻辑一致）"""
        if current_capacity < 900 and daily_demand <= 350:
            return "双机补库"
        elif daily_demand > 350:
            return "双机"
        else:
            return "单机"
    
    def calculate_flat_rpm(self, mode: str, daily_demand: float) -> int:
        """计算平段转速（Excel平段转速公式）"""
        if mode == "单机":
            # 单机模式计算公式
            demand_gap = daily_demand - 95  # 需求缺口
            flat_target_ratio = 0.75  # 平段目标比例
            flat_target_output = demand_gap * flat_target_ratio
            flat_required_load = flat_target_output / 106.875
            
            # 限制负荷率范围
            flat_required_load = max(0.62, min(1.0, flat_required_load))
            
            # 查找基准转速
            base_rpm = self.get_rpm_from_load(flat_required_load)
            
            # 限制转速范围并取20的倍数
            flat_rpm = max(450, min(630, round(base_rpm / 20) * 20))
        else:
            # 双机模式计算公式
            demand_gap = daily_demand - 190  # 需求缺口（双机）
            flat_target_ratio = 0.75  # 平段目标比例
            flat_target_output = demand_gap * flat_target_ratio
            flat_required_load = flat_target_output / 213.75  # 双机平段满负荷产量
            
            # 限制负荷率范围
            flat_required_load = max(0.62, min(1.0, flat_required_load))
            
            # 查找基准转速
            base_rpm = self.get_rpm_from_load(flat_required_load)
            
            # 限制转速范围并取20的倍数
            flat_rpm = max(450, min(630, round(base_rpm / 20) * 20))
        
        return flat_rpm
    
    def calculate_peak_rpm(self, mode: str, flat_rpm: int, daily_demand: float) -> int:
        """计算高峰转速（Excel高峰转速公式）"""
        flat_load = self.get_load_from_rpm(flat_rpm)
        
        if mode == "单机":
            # 单机模式
            flat_output = 106.875 * flat_load
            remaining_demand = daily_demand - 95 - flat_output
            peak_required_load = remaining_demand / 83.125
            
            # 限制负荷率范围
            peak_required_load = max(0.62, min(1.0, peak_required_load))
            
            # 查找基准转速
            base_rpm = self.get_rpm_from_load(peak_required_load)
            
            # 限制转速范围并取20的倍数
            peak_rpm = max(450, min(630, round(base_rpm / 20) * 20))
        else:
            # 双机模式
            flat_output = 213.75 * flat_load  # 双机平段产量
            remaining_demand = daily_demand - 190 - flat_output
            peak_required_load = remaining_demand / 166.25  # 双机高峰满负荷产量
            
            # 限制负荷率范围
            peak_required_load = max(0.62, min(1.0, peak_required_load))
            
            # 查找基准转速
            base_rpm = self.get_rpm_from_load(peak_required_load)
            
            # 限制转速范围并取20的倍数
            peak_rpm = max(450, min(630, round(base_rpm / 20) * 20))
        
        return peak_rpm
    
    def generate_weekly_plan(self, loading_data: List[float]) -> pd.DataFrame:
        """生成一周运行计划表（与Excel一致）"""
        days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        results = []
        
        current_capacity = self.default_params['current_capacity']
        empty_loss = self.default_params['empty_loss']
        
        for i, loading in enumerate(loading_data):
            # 计算日需求量
            daily_demand = loading + empty_loss
            
            # 确定运行模式
            mode = self.determine_mode(daily_demand, current_capacity)
            
            # 低谷转速固定为630
            valley_rpm = 630
            
            # 计算平段和高峰转速
            flat_rpm = self.calculate_flat_rpm(mode, daily_demand)
            peak_rpm = self.calculate_peak_rpm(mode, flat_rpm, daily_demand)
            
            # 计算负荷率
            flat_load_rate = self.get_load_from_rpm(flat_rpm)
            peak_load_rate = self.get_load_from_rpm(peak_rpm)
            
            # 计算预计产量
            estimated_output = self.calculate_daily_output(mode, flat_load_rate, peak_load_rate)
            
            # 计算罐容变化和期末罐容
            capacity_change = estimated_output - daily_demand
            end_capacity = current_capacity + capacity_change
            
            # 补库标志
            refill_flag = "是" if mode == "双机补库" else "否"
            
            # 罐容提醒
            if end_capacity > 1300:
                capacity_alert = "罐容偏高，注意控制"
            elif end_capacity < 900:
                capacity_alert = "罐容偏低，注意补充"
            else:
                capacity_alert = "正常"
            
            # 添加到结果
            results.append({
                "日期": days[i],
                "装车量(吨)": loading,
                "日需求量(吨)": round(daily_demand, 5),
                "当前罐容(吨)": round(current_capacity, 5),
                "运行模式": mode,
                "低谷转速(RPM)": valley_rpm,
                "平段转速(RPM)": flat_rpm,
                "高峰转速(RPM)": peak_rpm,
                "平段负荷率": round(flat_load_rate, 4),
                "高峰负荷率": round(peak_load_rate, 4),
                "预计产量(吨)": round(estimated_output, 1),
                "罐容变化(吨)": round(capacity_change, 1),
                "期末罐容(吨)": round(end_capacity, 1),
                "补库标志": refill_flag,
                "罐容提醒": capacity_alert
            })
            
            # 更新当前罐容为下一日的起始罐容
            current_capacity = end_capacity
        
        return pd.DataFrame(results)