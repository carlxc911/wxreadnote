from flask import Flask, render_template, request, send_file, jsonify
import os
import sys
import json
import tempfile
import traceback
from werkzeug.utils import secure_filename
from notebook_v1 import parse_cookie_string, get_notebooklist, get_bookinfo, get_chapter_info, get_bookmark_list, get_review_list, export_to_excel, export_to_json

# 检测是否在Vercel环境中运行
is_vercel = os.environ.get('VERCEL') == '1'

# 设置简单的日志记录
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 记录重要的环境信息
logger.info(f"Starting application in {'Vercel' if is_vercel else 'local'} environment")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Files in current directory: {os.listdir('.')}")

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'weread-exporter-secret-key!'

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    logger.info(f"Created upload folder: {UPLOAD_FOLDER}")

OUTPUT_DIR = 'outputs'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logger.info(f"Created output folder: {OUTPUT_DIR}")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传大小为16MB

# 在Vercel环境中，简化SocketIO相关功能
if not is_vercel:
    try:
        from flask_socketio import SocketIO, emit
        socketio = SocketIO(app, cors_allowed_origins="*")
        logger.info("Successfully initialized SocketIO")
    except ImportError:
        logger.warning("flask_socketio not available, using mock implementation")
        socketio = None
else:
    logger.info("Running in Vercel environment, using mock SocketIO implementation")
    socketio = None

# 辅助函数：安全的socket emit
def safe_emit(event, data, room=None):
    if socketio and not is_vercel:
        try:
            socketio.emit(event, data, room=room)
            return True
        except Exception as e:
            logger.error(f"Error emitting socket event: {str(e)}")
            return False
    return False

@app.route('/')
def index():
    logger.info("Serving index page")
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    logger.info("Extract endpoint called")
    try:
        # 获取cookie
        cookie = request.form.get('cookie', '')
        sid = request.form.get('sid', '')
        
        logger.info(f"Received request with sid: {sid[:5]}... (truncated)")
        
        if not cookie:
            logger.warning("No cookie provided")
            return jsonify({'status': 'error', 'message': '请输入有效的Cookie'}), 400
            
        # 创建临时目录用于存储导出文件
        temp_dir = tempfile.mkdtemp(dir=OUTPUT_DIR)
        logger.info(f"Created temp directory: {temp_dir}")
        
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
            logger.info(f"Accessing weread URL: {weread_url}")
            response = session.get(weread_url)
            logger.info(f"Weread response status: {response.status_code}")
            safe_emit('progress_update', {'status': 'connecting', 'message': '正在连接微信读书...'}, room=sid)
        except Exception as e:
            logger.error(f"Failed to access weread: {str(e)}")
            return jsonify({'status': 'error', 'message': f'访问微信读书主页失败: {str(e)}'}), 500
        
        # 获取笔记本列表
        safe_emit('progress_update', {'status': 'fetching_books', 'message': '正在获取书籍列表...'}, room=sid)
        
        try:
            logger.info("Fetching notebook list")
            books = get_notebooklist(session)
            if not books:
                logger.warning("No books found")
                return jsonify({'status': 'error', 'message': '获取书籍列表失败，请检查Cookie是否有效'}), 400
            
            logger.info(f"Found {len(books)} books")
        except Exception as e:
            logger.error(f"Error fetching notebook list: {str(e)}")
            return jsonify({'status': 'error', 'message': f'获取书籍列表失败: {str(e)}'}), 500
        
        # 发送总书籍数量
        total_books = len(books)
        safe_emit('progress_update', {
            'status': 'start_processing',
            'message': f'开始处理，共有 {total_books} 本书',
            'total_books': total_books,
            'current_book': 0,
            'percent': 0
        }, room=sid)
        
        all_books_data = []
        
        for index, book_item in enumerate(books):
            try:
                book = book_item.get('book')
                bookId = book.get('bookId')
                title = book.get('title', '未知书名')
                
                # 更新进度
                current_book = index + 1
                percent = int((current_book / total_books) * 100)
                logger.info(f"Processing book {current_book}/{total_books}: {title}")
                
                safe_emit('progress_update', {
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
                    logger.info(f"Book '{title}' has {len(bookmark_list_huaxian)} highlights")
                    safe_emit('progress_update', {
                        'status': 'processing_detail',
                        'message': f'《{title}》 - 获取到 {len(bookmark_list_huaxian)} 条划线'
                    }, room=sid)
                if reviews:
                    all_notes.extend(reviews)
                    logger.info(f"Book '{title}' has {len(reviews)} notes")
                    safe_emit('progress_update', {
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
            except Exception as e:
                logger.error(f"Error processing book '{title}': {str(e)}")
                logger.error(traceback.format_exc())
                # 继续处理下一本书
                continue
        
        # 导出数据
        safe_emit('progress_update', {
            'status': 'exporting',
            'message': '正在导出数据...',
            'percent': 95
        }, room=sid)
        
        timestamp = int(time.time())
        json_file = os.path.join(temp_dir, f'weread_notes_{timestamp}.json')
        excel_file = os.path.join(temp_dir, f'weread_notes_{timestamp}.xlsx')
        
        logger.info(f"Exporting data to JSON: {json_file}")
        export_to_json(all_books_data, json_file)
        
        logger.info(f"Exporting data to Excel: {excel_file}")
        export_to_excel(all_books_data, excel_file)
        
        # 完成
        safe_emit('progress_update', {
            'status': 'completed',
            'message': '处理完成！',
            'percent': 100
        }, room=sid)
        
        logger.info("Processing completed successfully")
        
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
        logger.error(f"Extraction failed: {str(e)}")
        logger.error(error_msg)
        
        if 'sid' in locals() and sid:
            safe_emit('progress_update', {
                'status': 'error',
                'message': f'处理出错: {str(e)}'
            }, room=sid)
        return jsonify({'status': 'error', 'message': f'处理过程中出错: {str(e)}', 'details': error_msg}), 500

@app.route('/download')
def download():
    logger.info("Download endpoint called")
    filename = request.args.get('file')
    dir_name = request.args.get('dir')
    
    if not filename or not dir_name:
        logger.warning("Invalid download parameters")
        return jsonify({'status': 'error', 'message': '无效的下载参数'}), 400
    
    # 安全检查
    filename = secure_filename(filename)
    if '..' in dir_name or '/' in dir_name:
        logger.warning(f"Invalid directory parameter: {dir_name}")
        return jsonify({'status': 'error', 'message': '无效的目录参数'}), 400
    
    file_path = os.path.join(OUTPUT_DIR, dir_name, filename)
    logger.info(f"Download file path: {file_path}")
    
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return jsonify({'status': 'error', 'message': '文件不存在'}), 404
    
    return send_file(file_path, as_attachment=True)

@app.route('/status', methods=['GET'])
def status():
    """简单的状态检查接口，用于验证应用是否运行正常"""
    logger.info("Status check called")
    return jsonify({
        'status': 'ok',
        'version': '1.0.0',
        'environment': 'vercel' if is_vercel else 'local',
        'python_version': sys.version,
        'directories': {
            'uploads': os.path.exists(UPLOAD_FOLDER),
            'outputs': os.path.exists(OUTPUT_DIR)
        }
    })

if not is_vercel:
    @socketio.on('connect')
    def handle_connect():
        logger.info("Client connected")
        emit('connected', {'sid': request.sid})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info("Client disconnected")

# 为Vercel部署添加WSGI应用入口点
if is_vercel:
    # 在Vercel上，直接使用Flask的WSGI应用
    application = app
else:
    # 在非Vercel环境下，使用SocketIO的WSGI应用
    if socketio:
        application = socketio.wsgi_app
    else:
        application = app

# 导出app对象供Vercel使用
app = application

if __name__ == '__main__':
    if not is_vercel and socketio:
        logger.info("Starting SocketIO application")
        socketio.run(app, debug=True)
    else:
        logger.info("Starting Flask application")
        app.run(debug=True) 
