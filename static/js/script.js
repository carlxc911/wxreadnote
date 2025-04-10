document.addEventListener('DOMContentLoaded', function() {
    const extractForm = document.getElementById('extractForm');
    const submitBtn = document.getElementById('submitBtn');
    const progressArea = document.getElementById('progressArea');
    const resultArea = document.getElementById('resultArea');
    const errorArea = document.getElementById('errorArea');
    const errorMessage = document.getElementById('errorMessage');
    const errorDetailsText = document.getElementById('errorDetailsText');
    const excelDownload = document.getElementById('excelDownload');
    const jsonDownload = document.getElementById('jsonDownload');
    const sidInput = document.getElementById('sid');
    const progressBar = document.getElementById('progressBar');
    const statusMessage = document.getElementById('statusMessage');
    const bookCounter = document.getElementById('bookCounter');
    const currentBookTitle = document.getElementById('currentBookTitle');
    const progressLog = document.getElementById('progressLog');
    
    // 连接WebSocket
    const socket = io();
    let socketConnected = false;
    
    // 监听连接事件
    socket.on('connect', function() {
        console.log('Connected to WebSocket server');
        socketConnected = true;
        addLogMessage('已连接到服务器');
    });
    
    socket.on('connected', function(data) {
        console.log('Received session ID:', data.sid);
        sidInput.value = data.sid;
    });
    
    // 监听进度更新事件
    socket.on('progress_update', function(data) {
        console.log('Progress update:', data);
        updateProgress(data);
    });
    
    // 监听断开连接事件
    socket.on('disconnect', function() {
        console.log('Disconnected from WebSocket server');
        socketConnected = false;
        addLogMessage('与服务器断开连接');
    });
    
    // 添加日志消息
    function addLogMessage(message) {
        const li = document.createElement('li');
        li.className = 'log-item';
        li.textContent = message;
        progressLog.appendChild(li);
        // 滚动到底部
        const logContainer = progressLog.parentElement;
        logContainer.scrollTop = logContainer.scrollHeight;
    }
    
    // 更新进度显示
    function updateProgress(data) {
        // 更新状态消息
        statusMessage.textContent = data.message || '';
        
        // 更新进度条
        if (data.percent !== undefined) {
            progressBar.style.width = `${data.percent}%`;
            progressBar.setAttribute('aria-valuenow', data.percent);
        }
        
        // 根据状态更新UI
        switch(data.status) {
            case 'connecting':
                addLogMessage('正在连接微信读书服务器...');
                break;
                
            case 'fetching_books':
                addLogMessage('正在获取书籍列表...');
                break;
                
            case 'start_processing':
                bookCounter.textContent = `0/${data.total_books}`;
                addLogMessage(`共找到 ${data.total_books} 本书籍，开始处理...`);
                break;
                
            case 'processing':
                // 更新书籍计数
                bookCounter.textContent = `${data.current_book}/${data.total_books}`;
                // 更新当前处理的书名
                currentBookTitle.textContent = data.book_title || '未知书名';
                // 添加日志
                addLogMessage(`正在处理: 《${data.book_title}》`);
                break;
                
            case 'processing_detail':
                // 添加处理详情日志
                addLogMessage(`  └─ ${data.message}`);
                break;
                
            case 'exporting':
                addLogMessage('正在导出数据...');
                break;
                
            case 'completed':
                addLogMessage('处理完成！可以下载文件了。');
                break;
                
            case 'error':
                addLogMessage(`错误: ${data.message}`);
                break;
        }
    }

    extractForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // 检查WebSocket连接
        if (!socketConnected) {
            alert('与服务器的连接已断开，请刷新页面后重试。');
            return;
        }
        
        // 重置显示状态
        resultArea.style.display = 'none';
        errorArea.style.display = 'none';
        progressLog.innerHTML = ''; // 清空日志
        
        // 显示进度区域
        progressArea.style.display = 'block';
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', 0);
        statusMessage.textContent = '正在连接服务器...';
        currentBookTitle.textContent = '等待开始...';
        bookCounter.textContent = '0/0';
        addLogMessage('开始处理，正在连接服务器...');
        
        // 禁用提交按钮
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
        
        // 获取表单数据
        const formData = new FormData(extractForm);
        
        // 发送请求
        fetch('/extract', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            // 隐藏进度条区域只有在成功时才执行，因为错误会在WebSocket中更新
            if (data.status === 'success') {
                // 显示结果区域
                resultArea.style.display = 'block';
                
                // 设置下载链接
                excelDownload.href = data.files.excel;
                jsonDownload.href = data.files.json;
            } else {
                // 显示错误信息
                errorArea.style.display = 'block';
                errorMessage.textContent = data.message || '处理过程中出错';
                
                if (data.details) {
                    errorDetailsText.textContent = data.details;
                } else {
                    document.querySelector('[data-bs-target="#errorDetails"]').style.display = 'none';
                }
            }
        })
        .catch(error => {
            // 显示错误信息
            errorArea.style.display = 'block';
            errorMessage.textContent = '网络错误，请稍后重试';
            errorDetailsText.textContent = error.toString();
            // 添加到日志
            addLogMessage(`网络错误: ${error.toString()}`);
        })
        .finally(() => {
            // 恢复提交按钮
            submitBtn.disabled = false;
            submitBtn.innerHTML = '开始提取';
        });
    });
}); 