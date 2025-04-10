import sys
import os

try:
    # 检查必要的库是否已安装
    import flask
    import requests
    import pandas
    
    # 检查必要的文件是否存在
    required_files = ['app.py', 'notebook_v1.py', 'templates/index.html', 
                     'static/css/style.css', 'static/js/script.js']
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print(f"错误: 以下文件不存在: {', '.join(missing_files)}")
        sys.exit(1)
    
    # 尝试引入应用
    from app import app
    
    print("应用检查成功，所有依赖和文件都正确配置。")
    print("可以通过运行 'python app.py' 启动应用。")
    
except ImportError as e:
    print(f"错误: 缺少必要的库: {e}")
    print("请运行 'pip install -r requirements.txt' 安装所有依赖。")
    sys.exit(1)
except Exception as e:
    print(f"错误: {e}")
    sys.exit(1) 