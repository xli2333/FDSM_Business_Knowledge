import os
import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import threading

# --- 1. 配置区域 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 新的保存目录
SAVE_ROOT = os.path.join(BASE_DIR, "锦缎")
# 链接文件路径
LINKS_FILE = os.path.join(BASE_DIR, "锦缎_links.txt")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

print_lock = threading.Lock()

def safe_print(msg):
    with print_lock:
        print(msg)

# --- 2. 工具函数 ---

def clean_filename(text):
    return re.sub(r'[\\/*?:\"<>|\n\t]', "", text).strip()

def determine_ext(url):
    """适配微信图片后缀"""
    if "wx_fmt=png" in url: return ".png"
    if "wx_fmt=gif" in url: return ".gif"
    if "wx_fmt=jpeg" in url or "wx_fmt=jpg" in url: return ".jpg"
    ext = os.path.splitext(url)[1]
    if ext and len(ext) <= 5: return ext
    return ".jpg"

def save_image(img_url, save_dir, index):
    try:
        if not img_url: return
        img_url = img_url.strip()
        
        # 处理协议相对路径 (//example.com/img.png)
        if img_url.startswith("//"):
            img_url = "https:" + img_url
            
        full_url = img_url if img_url.startswith("http") else urljoin("https://mp.weixin.qq.com", img_url)
        
        ext = determine_ext(full_url)
        img_name = f"image_{index}{ext}"
        save_path = os.path.join(save_dir, img_name)

        if os.path.exists(save_path): return

        # verify=False 有助于防止某些旧 SSL 问题，但对 WeChat 通常不需要，不过为了稳健加上
        resp = requests.get(full_url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
        else:
            safe_print(f"Warning: Image download failed {resp.status_code} - {full_url}")
    except Exception as e:
        safe_print(f"Warning: Image save error: {e} - {img_url}") 

def parse_detail_page(url, title, date):
    """
    解析内页：
    优先匹配微信结构 (js_content)，其次匹配官网结构 (detail-con)
    """
    try:
        # --- 1. 路径准备 ---
        # 确保日期格式正确，有时候可能是 YYYY-MM-DD
        if not date or len(date) < 7:
            date = "Unknown_Date"
        
        month_str = date[:7] 
        safe_title = clean_filename(title)[:50] 
        folder_name = f"{date}_{safe_title}"
        target_dir = os.path.join(SAVE_ROOT, month_str, folder_name)
        content_file = os.path.join(target_dir, "content.txt")

        # 断点续爬：如果内容文件已存在，跳过
        if os.path.exists(content_file):
           safe_print(f"   [跳过] (已存在) {safe_title}...")
           return

        # --- 2. 请求页面 ---
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = 'utf-8' # 微信通常是utf-8
        soup = BeautifulSoup(resp.text, 'html.parser')

        mode = "unknown"
        content_div = None
        
        # 1. 尝试找微信公众号正文容器
        content_div = soup.find('div', id='js_content') or soup.find('div', class_='rich_media_content')
        if content_div:
            mode = "wechat"
        else:
            # 2. 如果没找到，再尝试找学校官网或其他通用容器（以防万一链接不是微信的）
            content_div = soup.find('div', class_='detail-con')
            if content_div:
                mode = "school_native"
        
        if not content_div:
            # Fallback (Enhanced): 针对特殊结构或纯图片文章
            safe_print(f"   [尝试] {safe_title} -> 未找到标准正文，尝试全局搜索图片...")
            
            # 策略：直接提取所有含有 mmbiz.qpic.cn 的图片
            candidate_imgs = []
            for img in soup.find_all('img'):
                src = img.get('src')
                data_src = img.get('data-src')
                
                # 优先检查 src 和 data-src
                url_to_use = None
                if src and "mmbiz.qpic.cn" in src:
                    url_to_use = src
                elif data_src and "mmbiz.qpic.cn" in data_src:
                    url_to_use = data_src
                
                if url_to_use:
                     candidate_imgs.append(url_to_use)

            if candidate_imgs:
                 # 去重
                 candidate_imgs = list(set(candidate_imgs))
                 mode = "wechat_fallback_global"
                 
                 os.makedirs(target_dir, exist_ok=True)
                 
                 # 重新写入内容文件
                 with open(content_file, 'w', encoding='utf-8') as f:
                    f.write(f"标题: {title}\n")
                    f.write(f"日期: {date}\n")
                    f.write(f"链接: {url}\n")
                    f.write(f"来源模式: {mode} (Fallback Global)\n")
                    f.write("-" * 40 + "\n\n")
                    f.write(f"此页面触发全局图片搜索模式，共找到 {len(candidate_imgs)} 张图片。")

                 img_count = 0
                 for i, img_url in enumerate(candidate_imgs):
                     save_image(img_url, target_dir, i+1)
                     img_count += 1
                 
                 safe_print(f" [成功] {date} | {safe_title}... [{mode} | 图:{img_count}]")
                 return
            else:
                safe_print(f"   [警告] {safe_title} -> 无法识别页面结构且未找到图片 (URL: {url})")
                return

        # 创建文件夹
        os.makedirs(target_dir, exist_ok=True)

        # 提取文字
        text_content = content_div.get_text(separator="\n", strip=True)

        # 保存文本
        with open(content_file, 'w', encoding='utf-8') as f:
            f.write(f"标题: {title}\n")
            f.write(f"日期: {date}\n")
            f.write(f"链接: {url}\n")
            f.write(f"来源模式: {mode}\n")
            f.write("-" * 40 + "\n\n")
            f.write(text_content)

        # 提取图片
        images = content_div.find_all('img')
        img_count = 0
        for i, img in enumerate(images):
            src = ""
            if mode == "wechat":
                # 微信模式：必须优先取 data-src
                src = img.get('data-src') or img.get('src')
            else:
                # 其他模式：优先取 src
                src = img.get('src')
            
            if src:
                save_image(src, target_dir, i+1)
                img_count += 1
        
        safe_print(f" [成功] {date} | {safe_title}... [{mode} | 图:{img_count}]")

    except Exception as e:
        safe_print(f" [错误] {title} 解析失败: {e}")

def process_item(line):
    line = line.strip()
    if not line: return

    try:
        # 文件格式: 2025-12-19 | 标题... | http://...
        parts = line.split(" | ")
        if len(parts) < 3:
            return

        date = parts[0].strip()
        title = parts[1].strip()
        url = parts[2].strip()
        
        # 简单的 URL 校验
        if not url.startswith("http"):
            return

        parse_detail_page(url, title, date)

    except Exception as e:
        safe_print(f"处理行出错: {line[:30]}... -> {e}")

if __name__ == "__main__":
    if not os.path.exists(SAVE_ROOT): os.makedirs(SAVE_ROOT)
    
    if not os.path.exists(LINKS_FILE):
        print(f"错误: 找不到链接文件 {LINKS_FILE}")
        exit(1)

    print("="*60)
    print(f"保存路径: {SAVE_ROOT}")
    print(f"读取文件: {LINKS_FILE}")
    print("="*60)

    # 读取所有行
    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    MAX_WORKERS = 5 # 并发数
    
    print(f"共发现 {len(lines)} 条链接，开始处理...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        futures = [executor.submit(process_item, line) for line in lines]
        
        # 等待完成 (可选: 如果需要进度条，可以使用 as_completed)
        for future in futures:
            try: future.result()
            except: pass

    print("\n所有链接处理完成！")
