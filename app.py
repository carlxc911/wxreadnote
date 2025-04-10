from flask import Flask, render_template, request, send_file, jsonify
import os
import json
import tempfile
import traceback
from werkzeug.utils import secure_filename
from notebook_v1 import parse_cookie_string, get_notebooklist, get_bookinfo, get_chapter_info, get_bookmark_list, get_review_list, export_to_excel, export_to_json

# 检测是否在Vercel环境中运行
is_vercel = os.environ.get('VERCEL', False)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'weread-exporter-secret-key!'

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

OUTPUT_DIR = 'outputs'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传大小为16MB

# 只在非Vercel环境中使用SocketIO
if not is_vercel:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*")
else:
    # 在Vercel环境中创建一个模拟的socketio对象
    class MockSocketIO:
        def __init__(self):
            pass
        
        def emit(self, event, data, room=None):
            pass
        
        def run(self, app, **kwargs):
            pass
        
        @property
        def wsgi_app(self):
            return app.wsgi_app
    
    socketio = MockSocketIO()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    try:
        # 获取cookie
        cookie = request.form.get('cookie', '')
        # 获取Session ID用于WebSocket通信
        sid = request.form.get('sid', '')
        
        if not cookie:
            return jsonify({'status': 'error', 'message': '请输入有效的Cookie'}), 400
            
        # 创建临时目录用于存储导出文件
        temp_dir = tempfile.mkdtemp(dir=OUTPUT_DIR)
        
        # 获取用户的User-Agent
        user_agent = request.headers.get('User-Agent', '')
        if not user_agent:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        # 创建会话
        import requests
        session = requests.Session()
        session.cookies = parse_cookie_string(cookie)
        session.headers.update({'User-Agent': user_agent})
        
        # 访问主页获取必要的cookie
        try:
            weread_url = "https://weread.qq.com/"
            session.get(weread_url)
            if not is_vercel:
                socketio.emit('progress_update', {'status': 'connecting', 'message': '正在连接微信读书...'}, room=sid)
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'访问微信读书主页失败: {str(e)}'}), 500
        
        # 获取笔记本列表
        if not is_vercel:
            socketio.emit('progress_update', {'status': 'fetching_books', 'message': '正在获取书籍列表...'}, room=sid)
        books = get_notebooklist(session)
        if not books:
            return jsonify({'status': 'error', 'message': '获取书籍列表失败，请检查Cookie是否有效'}), 400
        
        # 发送总书籍数量
        total_books = len(books)
        if not is_vercel:
            socketio.emit('progress_update', {
                'status': 'start_processing',
                'message': f'开始处理，共有 {total_books} 本书',
                'total_books': total_books,
                'current_book': 0,
                'percent': 0
            }, room=sid)
        
        all_books_data = []
        
        for index, book_item in enumerate(books):
            book = book_item.get('book')
            bookId = book.get('bookId')
            title = book.get('title', '未知书名')
            
            # 更新进度
            current_book = index + 1
            percent = int((current_book / total_books) * 100)
            if not is_vercel:
                socketio.emit('progress_update', {
                    'status': 'processing',
                    'message': f'正在处理 ({current_book}/{total_books}): {title}',
                    'current_book': current_book,
                    'book_title': title,
                    'total_books': total_books,
                    'percent': percent
                }, room=sid)
            
            # 获取书籍详细信息
            isbn, rating, book_info = get_bookinfo(session, bookId)
            chapter_info = get_chapter_info(session, bookId)
            
            # 划线列表清洗
            bookmark_list = get_bookmark_list(session, bookId)
            if bookmark_list:
                bookmark_list_huaxian = [item for item in bookmark_list if item.get('type') == 1]
            else:
                bookmark_list_huaxian = []
                
            # 书评和笔记
            summary, reviews = get_review_list(session, bookId)

            # 合并划线和笔记
            all_notes = []
            if bookmark_list_huaxian:
                all_notes.extend(bookmark_list_huaxian)
                if not is_vercel:
                    socketio.emit('progress_update', {
                        'status': 'processing_detail',
                        'message': f'《{title}》 - 获取到 {len(bookmark_list_huaxian)} 条划线'
                    }, room=sid)
            if reviews:
                all_notes.extend(reviews)
                if not is_vercel:
                    socketio.emit('progress_update', {
                        'status': 'processing_detail',
                        'message': f'《{title}》 - 获取到 {len(reviews)} 条笔记'
                    }, room=sid)
            
            # 排序
            if all_notes:
                all_notes = sorted(
                    all_notes,
                    key=lambda x: (
                        x.get("chapterUid", 1),
                        (
                            0
                            if (
                                x.get("range", "") == ""
                                or x.get("range", "").split("-")[0] == ""
                            )
                            else int(x.get("range", "0-0").split("-")[0])
                        ),
                    ),
                )
            
            # 添加章节信息
            for note in all_notes:
                chapterUid = note.get("chapterUid", 1)
                if chapter_info and chapterUid in chapter_info:
                    note["chapter_title"] = chapter_info[chapterUid].get("title", "")
                else:
                    note["chapter_title"] = ""
            
            # 添加书籍数据
            book_data = {
                "book_info": book,
                "isbn": isbn,
                "rating": rating,
                "notes": all_notes,
                "summary": summary
            }
            
            all_books_data.append(book_data)
            
            # 每处理一本书睡眠1秒，避免请求过快
            import time
            time.sleep(1)
        
        # 导出数据
        if not is_vercel:
            socketio.emit('progress_update', {
                'status': 'exporting',
                'message': '正在导出数据...',
                'percent': 95
            }, room=sid)
        
        timestamp = int(time.time())
        json_file = os.path.join(temp_dir, f'weread_notes_{timestamp}.json')
        excel_file = os.path.join(temp_dir, f'weread_notes_{timestamp}.xlsx')
        
        export_to_json(all_books_data, json_file)
        export_to_excel(all_books_data, excel_file)
        
        # 完成
        if not is_vercel:
            socketio.emit('progress_update', {
                'status': 'completed',
                'message': '处理完成！',
                'percent': 100
            }, room=sid)
        
        return jsonify({
            'status': 'success', 
            'message': '数据导出成功',
            'files': {
                'excel': f'/download?file=weread_notes_{timestamp}.xlsx&dir={os.path.basename(temp_dir)}',
                'json': f'/download?file=weread_notes_{timestamp}.json&dir={os.path.basename(temp_dir)}'
            }
        })
        
    except Exception as e:
        error_msg = traceback.format_exc()
        if 'sid' in locals() and sid:
            if not is_vercel:
                socketio.emit('progress_update', {
                    'status': 'error',
                    'message': f'处理出错: {str(e)}'
                }, room=sid)
        return jsonify({'status': 'error', 'message': f'处理过程中出错: {str(e)}', 'details': error_msg}), 500

@app.route('/download')
def download():
    filename = request.args.get('file')
    dir_name = request.args.get('dir')
    
    if not filename or not dir_name:
        return jsonify({'status': 'error', 'message': '无效的下载参数'}), 400
    
    # 安全检查
    filename = secure_filename(filename)
    if '..' in dir_name or '/' in dir_name:
        return jsonify({'status': 'error', 'message': '无效的目录参数'}), 400
    
    file_path = os.path.join(OUTPUT_DIR, dir_name, filename)
    
    if not os.path.exists(file_path):
        return jsonify({'status': 'error', 'message': '文件不存在'}), 404
    
    return send_file(file_path, as_attachment=True)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# 为Vercel部署添加WSGI应用入口点
if is_vercel:
    # 在Vercel上，直接使用Flask的WSGI应用
    application = app
else:
    # 在非Vercel环境下，使用SocketIO的WSGI应用
    application = socketio.wsgi_app

# 导出app对象供Vercel使用
app = application

if __name__ == '__main__':
    if not is_vercel:
        socketio.run(app, debug=True)
    else:
        app.run(debug=True) 