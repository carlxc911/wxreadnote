#!/usr/bin/env python
"""
清理脚本，用于定期删除outputs目录中的旧文件
可以通过cron作业定期运行
示例: 0 0 * * * /path/to/venv/bin/python /path/to/app/cleanup.py
"""

import os
import time
import shutil
from datetime import datetime

# 配置
OUTPUT_DIR = 'outputs'
MAX_AGE_HOURS = 24  # 文件最大保留时间（小时）

def cleanup():
    """清理超过指定时间的导出文件"""
    print(f"开始清理 {OUTPUT_DIR} 目录中超过 {MAX_AGE_HOURS} 小时的文件...")
    
    if not os.path.exists(OUTPUT_DIR):
        print(f"目录 {OUTPUT_DIR} 不存在，无需清理")
        return
    
    current_time = time.time()
    max_age_seconds = MAX_AGE_HOURS * 3600
    
    # 统计清理前的文件数量
    total_files_before = sum([len(files) for _, _, files in os.walk(OUTPUT_DIR)])
    
    # 遍历并删除过期的文件和目录
    for item in os.listdir(OUTPUT_DIR):
        item_path = os.path.join(OUTPUT_DIR, item)
        
        # 获取最后修改时间
        mtime = os.path.getmtime(item_path)
        age_seconds = current_time - mtime
        
        # 如果超过最大保留时间则删除
        if age_seconds > max_age_seconds:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"已删除目录: {item_path}")
            else:
                os.remove(item_path)
                print(f"已删除文件: {item_path}")
    
    # 统计清理后的文件数量
    total_files_after = sum([len(files) for _, _, files in os.walk(OUTPUT_DIR)])
    
    print(f"清理完成。删除了 {total_files_before - total_files_after} 个文件，当前剩余 {total_files_after} 个文件")
    print(f"清理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    cleanup() 