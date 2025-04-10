from flask import Flask, render_template, request, jsonify, send_file
import os
import sys
import json
import tempfile
import traceback
import time
import requests
from werkzeug.utils import secure_filename

# 设置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 记录环境信息
logger.info(f"Starting Vercel-compatible application")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Files in current directory: {os.listdir('.')}")

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'weread-exporter-secret-key!'

# 配置文件夹
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    logger.info(f"Created upload folder: {UPLOAD_FOLDER}")

OUTPUT_DIR = 'outputs'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    logger.info(f"Created output folder: {OUTPUT_DIR}")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制

# 从notebook_v1.py中提取的必要函数，移除pandas依赖
def parse_cookie_string(cookie_string):
    """解析cookie字符串为Cookie对象"""
    from http.cookies import SimpleCookie
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    
    for key, morsel in cookie.items():
        cookies_dict[key] = morsel.value
    
    return cookies_dict

def get_notebooklist(session):
    """获取笔记本列表"""
    url = "https://i.weread.qq.com/user/notebooks"
    response = session.get(url)
    
    if response.status_code == 200:
        return response.json().get('notebooks', [])
    return []

def get_bookinfo(session, bookId):
    """获取书籍信息"""
    url = f"https://i.weread.qq.com/book/info?bookId={bookId}"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        isbn = data.get('isbn', '')
        rating = data.get('newRating', 0)
        return isbn, rating, data
    return "", 0, {}

def get_chapter_info(session, bookId):
    """获取章节信息"""
    url = f"https://i.weread.qq.com/book/chapterInfos?bookId={bookId}"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        chapters = data.get('data', [])
        chapter_info = {}
        
        for chapter in chapters:
            chapter_info[chapter.get('chapterUid')] = chapter
        
        return chapter_info
    return {}

def get_bookmark_list(session, bookId):
    """获取划线列表"""
    url = f"https://i.weread.qq.com/book/bookmarklist?bookId={bookId}"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data.get('updated', [])
    return []

def get_review_list(session, bookId):
    """获取笔记列表"""
    url = f"https://i.weread.qq.com/review/list?bookId={bookId}"
    response = session.get(url)
    
    if response.status_code == 200:
        data = response.json()
        summary = data.get('summary', {})
        reviews = data.get('reviews', [])
        return summary, reviews
    return {}, []

def export_to_json(books_data, output_file):
    """导出为JSON格式"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(books_data, f, ensure_ascii=False, indent=4)
    return True

@app.route('/')
def index():
    logger.info("Serving index page")
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def status():
    """状态检查接口"""
    logger.info("Status check called")
    return jsonify({
        'status': 'ok',
        'version': '1.0.0 (Vercel)',
        'environment': 'vercel',
        'python_version': sys.version,
        'directories': {
            'uploads': os.path.exists(UPLOAD_FOLDER),
            'outputs': os.path.exists(OUTPUT_DIR)
        }
    })

@app.route('/extract', methods=['POST'])
def extract():
    logger.info("Extract endpoint called")
    try:
        # 获取cookie
        cookie = request.form.get('cookie', '')
        
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
        session = requests.Session()
        session.cookies = parse_cookie_string(cookie)
        session.headers.update({'User-Agent': user_agent})
        
        # 访问主页获取必要的cookie
        try:
            weread_url = "https://weread.qq.com/"
            logger.info(f"Accessing weread URL: {weread_url}")
            response = session.get(weread_url)
            logger.info(f"Weread response status: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to access weread: {str(e)}")
            return jsonify({'status': 'error', 'message': f'访问微信读书主页失败: {str(e)}'}), 500
        
        # 获取笔记本列表
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
                if reviews:
                    all_notes.extend(reviews)
                    logger.info(f"Book '{title}' has {len(reviews)} notes")
                
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
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error processing book '{title}': {str(e)}")
                logger.error(traceback.format_exc())
                # 继续处理下一本书
                continue
        
        # 导出数据
        timestamp = int(time.time())
        json_file = os.path.join(temp_dir, f'weread_notes_{timestamp}.json')
        
        logger.info(f"Exporting data to JSON: {json_file}")
        export_to_json(all_books_data, json_file)
        
        logger.info("Processing completed successfully")
        
        return jsonify({
            'status': 'success', 
            'message': '数据导出成功',
            'files': {
                'json': f'/download?file=weread_notes_{timestamp}.json&dir={os.path.basename(temp_dir)}'
            },
            'note': 'Vercel环境中仅支持JSON导出，完整功能请在本地运行'
        })
        
    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"Extraction failed: {str(e)}")
        logger.error(error_msg)
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

# 导出app对象供Vercel使用
application = app

if __name__ == '__main__':
    app.run(debug=True) 