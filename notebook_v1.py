import json
import os
import requests
import pandas as pd
from http.cookies import SimpleCookie
from requests.utils import cookiejar_from_dict
import re
from datetime import datetime
import time

# 从原项目复制必要的 API 常量和辅助函数
WEREAD_URL = "https://weread.qq.com/"  # 修复了URL末尾有额外空格的问题
WEREAD_NOTEBOOKS_URL = "https://i.weread.qq.com/user/notebooks"  # 修复了URL末尾有额外空格的问题
WEREAD_BOOKMARKLIST_URL = "https://i.weread.qq.com/book/bookmarklist"  # 修复了URL末尾有额外空格的问题
WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/book/chapterInfos"  # 修复了URL末尾有额外空格的问题
WEREAD_READ_INFO_URL = "https://i.weread.qq.com/book/readinfo"  # 修复了URL末尾有额外空格的问题
WEREAD_REVIEW_LIST_URL = "https://i.weread.qq.com/review/list"  # 修复了URL末尾有额外空格的问题
WEREAD_BOOK_INFO = "https://i.weread.qq.com/book/info"  # 修复了URL末尾有额外空格的问题

# 添加UA模拟正常浏览器访问
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# 添加输出目录
OUTPUT_DIR = "outputs"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 复制需要的函数
def parse_cookie_string(cookie_string):
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    cookiejar = None
    for key, morsel in cookie.items():
        cookies_dict[key] = morsel.value
        cookiejar = cookiejar_from_dict(cookies_dict, cookiejar=None, overwrite=True)
    return cookiejar

#获取划线列表
def get_bookmark_list(session, bookId):
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOKMARKLIST_URL, params=params)
    if r.ok:
        updated = r.json().get("updated")
        updated = sorted(
            updated,
            key=lambda x: (x.get("chapterUid", 1), int(x.get("range").split("-")[0])),
        )
        return r.json()["updated"]
    return None

#获取阅读信息（进度、阅读时间等）
def get_read_info(session, bookId):
    params = dict(bookId=bookId, readingDetail=1, readingBookIndex=1, finishedDate=1)
    r = session.get(WEREAD_READ_INFO_URL, params=params)
    if r.ok:
        return r.json()
    return None

#获取书籍的 ISBN 和评分
def get_bookinfo(session, bookId):
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOK_INFO, params=params)
    isbn = ""
    if r.ok:
        data = r.json()
        isbn = data.get("isbn", "")
        newRating = data.get("newRating", 0) / 1000
        return (isbn, newRating, data)
    else:
        print(f"get {bookId} book info failed")
        return ("", 0, {})

#获取笔记和点评
def get_review_list(session, bookId):
    params = dict(bookId=bookId, listType=11, mine=1, syncKey=0)
    r = session.get(WEREAD_REVIEW_LIST_URL, params=params)
    if not r.ok:
        return [], []
    
    reviews = r.json().get("reviews", [])
    summary = list(filter(lambda x: x.get("review", {}).get("type") == 4, reviews))
    reviews = list(filter(lambda x: x.get("review", {}).get("type") == 1, reviews))
    reviews = list(map(lambda x: x.get("review"), reviews))
    reviews = list(map(lambda x: {**x, "markText": x.pop("content")}, reviews))
    return summary, reviews

#获取章节信息
def get_chapter_info(session, bookId):
    body = {"bookIds": [bookId], "synckeys": [0], "teenmode": 0}
    r = session.post(WEREAD_CHAPTER_INFO, json=body)
    if (
        r.ok
        and "data" in r.json()
        and len(r.json()["data"]) == 1
        and "updated" in r.json()["data"][0]
    ):
        update = r.json()["data"][0]["updated"]
        return {item["chapterUid"]: item for item in update}
    return None

#笔记本列表
def get_notebooklist(session):
    # 增加重试机制
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            r = session.get(WEREAD_NOTEBOOKS_URL)
            print(f"笔记本列表请求状态码: {r.status_code}")
            
            if r.ok:
                data = r.json()
                books = data.get("books")
                if books:
                    books.sort(key=lambda x: x["sort"])
                    return books
                else:
                    print(f"获取到的数据中没有books字段: {data}")
            else:
                print(f"请求笔记本列表失败: {r.text}")
            
            retry_count += 1
            time.sleep(2)  # 等待2秒后重试
        except Exception as e:
            print(f"获取笔记本列表出错: {e}")
            retry_count += 1
            time.sleep(2)  # 等待2秒后重试
    
    return None
    
# 添加导出到JSON的函数
def export_to_json(data, filename=None):
    """导出数据到JSON文件"""
    if filename is None:
        filename = os.path.join(OUTPUT_DIR, 'weread_notes.json')
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已成功导出到 {filename}")

# 添加导出到Excel的函数
def export_to_excel(data, filename=None):
    """导出数据到Excel文件"""
    if filename is None:
        filename = os.path.join(OUTPUT_DIR, 'weread_notes.xlsx')
        
    notes_data = []
    for book in data:
        book_info = book['book_info']
        book_name = book_info.get('title', '')
        book_author = book_info.get('author', '')
        
        for note in book['notes']:
            chapter_title = note.get('chapter_title', '')
            if note.get('reviewId'):
                note_type = '笔记'
                huaxian_text = note.get('abstract', '') or note.get('markText', '')
                biji_text = note.get('content', '')
            else:
                note_type = '划线'
                huaxian_text = note.get('markText', '')
                biji_text = ''
            
            created_time = datetime.fromtimestamp(note.get('createTime', 0)).strftime('%Y-%m-%d %H:%M:%S')
            
            notes_data.append({
                '书名': book_name,
                '作者': book_author,
                '章节': chapter_title,
                '划线': huaxian_text,
                '笔记': biji_text,
                '创建时间': created_time
            })
    
    # 如果没有笔记数据，添加一个空行
    if not notes_data:
        notes_data.append({
            '书名': '', '作者': '', '章节': '', 
            '划线': '', '笔记': '', '创建时间': ''
        })
    
    df = pd.DataFrame(notes_data)
    df.to_excel(filename, index=False)
    print(f"数据已成功导出到 {filename}")
    
# 主程序
def main():
    # 获取微信读书Cookie
    print("开始执行微信读书笔记导出程序...")
    
    # 尝试从环境变量或文件读取cookie
    cookie = os.environ.get('WEREAD_COOKIE', '')
    
    # 如果环境变量中没有，尝试从cookie.txt文件读取
    if not cookie:
        try:
            if os.path.exists('cookie.txt'):
                with open('cookie.txt', 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                print("已从cookie.txt文件读取cookie")
        except Exception as e:
            print(f"读取cookie.txt文件失败: {e}")
    
    # 如果仍然没有cookie，使用默认值
    if not cookie:
        print("未找到环境变量或cookie.txt文件中的cookie，使用默认值")
        cookie = 'RK=EGkBQo7OVo; ptcz=30990c5a166d2e5fa778218e2955a59f3782743e05dbef9ffca65a77478fed79; wr_gid=277265037; wr_fp=1508329528; wr_skey=Mc0g93wI; wr_vid=76222150; wr_rt=web%40cLbwioS7YuknQUUt1Jl_AL'
    
    # 创建会话并添加UA
    session = requests.Session()
    session.cookies = parse_cookie_string(cookie)
    session.headers.update({'User-Agent': USER_AGENT})
    
    # 首先访问主页获取必要的cookie
    print("访问微信读书主页...")
    try:
        r = session.get(WEREAD_URL)
        print(f"访问主页状态码: {r.status_code}")
    except Exception as e:
        print(f"访问主页出错: {e}")
    
    # 获取笔记本列表
    print("获取笔记本列表...")
    books = get_notebooklist(session)
    if not books:
        print("获取书籍列表失败，请检查Cookie是否有效")
        print("当前使用的Cookie为:")
        print(cookie)
        print("提示: 请重新获取Cookie并保存到cookie.txt文件中，或在运行时设置WEREAD_COOKIE环境变量")
        return
    
    print(f"成功获取到 {len(books)} 本书的信息")
    all_books_data = []
    
    for index, book_item in enumerate(books):
        book = book_item.get('book')
        bookId = book.get('bookId')
        title = book.get('title')
        
        print(f"正在处理 {title}，一共{len(books)}本，当前是第{index+1}本。")

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
        if reviews:
            all_notes.extend(reviews)
        
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
    
    # 导出数据
    json_file = os.path.join(OUTPUT_DIR, 'weread_notes.json')
    excel_file = os.path.join(OUTPUT_DIR, 'weread_notes.xlsx')
    
    export_to_json(all_books_data, json_file)
    export_to_excel(all_books_data, excel_file)
    
    print("所有操作已完成！")

if __name__ == "__main__":
    main() 