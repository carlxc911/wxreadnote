# 微信读书笔记导出工具

这是一个网页版微信读书笔记导出工具，可以帮助用户导出微信读书中的笔记、划线和评论，并转换为Excel或JSON格式。

## 功能特点

- 网页界面：用户友好的web界面，无需安装任何软件
- 多格式导出：支持导出为Excel和JSON格式
- 安全性：所有数据处理都在服务器端进行，不会存储用户Cookie
- 完整笔记：导出包含书名、作者、章节、划线内容、笔记内容等完整信息
- 降低风险：使用用户自己的浏览器User-Agent，降低被封禁风险

## 本地运行

### 环境要求

- Python 3.7+
- pip 包管理器

### 安装步骤

1. 克隆仓库

```bash
git clone https://github.com/yourusername/weread-exporter.git
cd weread-exporter
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 运行应用

```bash
python app.py
```

4. 访问应用

打开浏览器访问 `http://127.0.0.1:5000`

## 使用方法

1. 登录 [微信读书网页版](https://weread.qq.com/)
2. 使用浏览器开发者工具获取 Cookie:
   - Chrome浏览器: 按F12 → 应用 → Cookie
   - Firefox浏览器: 按F12 → 存储 → Cookie
3. 复制所有Cookie文本（通常以 `wr_vid=xxx; wr_skey=xxx; ...` 格式）
4. 粘贴到工具提供的输入框中
5. 点击"开始提取"按钮
6. 处理完成后，下载Excel或JSON格式的笔记文件

## 部署到个人网站

### Docker部署 (推荐)

1. 构建Docker镜像

```bash
docker build -t weread-exporter .
```

2. 运行Docker容器

```bash
docker run -d -p 8000:8000 --name weread-exporter weread-exporter
```

3. 访问应用: `http://your-server-ip:8000`

### 普通web服务器部署

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 使用Gunicorn运行应用

```bash
gunicorn --bind 0.0.0.0:8000 app:app
```

3. 配置Nginx (可选，但推荐)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header User-Agent $http_user_agent;
    }
}
```

注意：在Nginx配置中，我们添加了 `proxy_set_header User-Agent $http_user_agent;` 以确保用户的浏览器信息能正确传递给后端应用。

## 常见问题

### 1. 关于Cookie和用户信息安全

- 本工具不会存储用户的Cookie信息
- 所有数据处理都在服务器端进行，不会将数据发送到第三方服务器
- 生成的文件会在下载后从服务器删除

### 2. 微信读书访问信息

当用户通过本工具访问微信读书API时：
- 请求会从服务器端发出，使用用户提供的Cookie
- 系统会使用用户自己的浏览器User-Agent访问微信读书API，而不是统一的User-Agent
- 对微信读书服务器而言，请求来源是托管本工具的服务器IP，但User-Agent是用户自己的，这降低了被检测和封禁的风险

### 3. 数据处理和性能

- 处理时间取决于用户笔记的数量，一般不超过2分钟
- 为避免请求过快，处理每本书会间隔1秒

## 贡献

欢迎提交Pull Request或Issues！

## 许可证

MIT 