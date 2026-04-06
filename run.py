import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import json
from tqdm import tqdm
from collections import Counter
import sqlite3

# =========================
# 0. 全局配置与辅助函数
# =========================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json"
}
api_url = "https://api2.openreview.net/notes"
domain = "ICLR.cc/2026/Conference"

def get_val(content_dict, field):
    """安全提取 API V2 的嵌套 value"""
    if not isinstance(content_dict, dict):
        return None
    v = content_dict.get(field, {})
    return v.get("value") if isinstance(v, dict) else v

def extract_number(val):
    """从诸如 '8: accept, good paper' 中提取整数"""
    if not val: return 0
    val_str = str(val)
    try:
        return int(val_str.split(":")[0])
    except:
        return 0

# =========================
# 1. 网页解析 (Task 1a-1d)
# =========================
url = f"https://openreview.net/group?id={domain}"
print(f"正在访问: {url}")

# 1a-1c: 请求网页并使用 BeautifulSoup 提取
try:
    res = requests.get(url, headers=headers)
    res.encoding = 'utf-8'
    with open("iclr_home.html", "w", encoding="utf-8") as f:
        f.write(res.text)
    
    soup = BeautifulSoup(res.text, "html.parser")
    print(f"1b. <title> 内容: {soup.title.text if soup.title else 'N/A'}")
    
    # 1c. 尝试用 bs4 提取静态页面中的信息 (注: 现代页面多为动态加载, bs4 可能提取不到完整数据, 需结合观察说明)
    print("1c. BeautifulSoup 提取结果:")
    venue_info = soup.find("div", id="header")
    if venue_info:
        print("找到包含信息的 div，但具体内容可能需依赖 JS 渲染。")
    else:
        print("未直接在初始 HTML 中提取到完整的会议时间地点(属于动态渲染)。")
except Exception as e:
    print(f"请求失败: {e}")

# 1d. Selenium 动态提取
print("\n1d. 正在启动 Selenium 提取会议动态信息...")
# 建议在 Windows 环境下保持 ChromeDriver 路径正确，Edge 也可
options = webdriver.ChromeOptions()
options.add_argument('--headless') # 开启无头模式，避免弹出浏览器窗口
driver = webdriver.Chrome(options=options) 
driver.get(url)
time.sleep(5) # 给足 JS 渲染时间
try:
    location = driver.find_element(By.CLASS_NAME, "venue-location").text
    date = driver.find_element(By.CLASS_NAME, "venue-date").text
    website = driver.find_element(By.CLASS_NAME, "venue-website").text
    print(f"Selenium 提取成功 -> 地点: {location}, 时间: {date}, 网址: {website}")
except Exception as e:
    print("Selenium 提取信息失败，请检查网络或页面元素是否加载完全。")
finally:
    driver.quit()

# =========================
# 2. 获取论文数据 (Task 2a-2c)
# =========================
all_papers = []
target_invitation = f"{domain}/-/Submission"
print(f"\n2a. 开始从 API 抓取论文原始数据: {target_invitation}")

# 分页获取 1000 篇数据
for offset in tqdm(range(0, 1000, 50), desc="抓取论文列表"):
    params = {
        "invitation": target_invitation,
        "limit": 50,
        "offset": offset
    }
    response = requests.get(api_url, params=params, headers=headers)
    if response.status_code == 200:
        notes = response.json().get("notes", [])
        all_papers.extend(notes)
        if len(notes) < 50:
            break # 已读完
    time.sleep(0.5) # 严格按照实验文档要求：暂停0.5秒防止被拦截

with open("paper_info_api_response.json", "w", encoding="utf-8") as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

# 2b. 清洗核心字段
print("2b. 开始清洗提取核心字段...")
cleaned_papers = []
for p in all_papers:
    c = p.get("content", {})
    cleaned_papers.append({
        "id": p.get("id"),
        "title": get_val(c, "title"),
        "authors": get_val(c, "authors"),
        "authorids": get_val(c, "authorids"),
        "keywords": get_val(c, "keywords"),
        "primary_area": get_val(c, "primary_area"),
        "number": p.get("number") or get_val(c, "number"),  # ✅ 优先从最外层获取
        "venue": p.get("venue") or get_val(c, "venue"),
        "venueid": p.get("venueid")
    })

with open("paper_info_cleaned.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_papers, f, indent=2, ensure_ascii=False)

# 2c. 分类数量统计
categories = ["Accept (Oral)", "Accept (Poster)", "Conditional Accept (Oral)", 
              "Conditional Accept (Poster)", "Reject", "Withdrawn Submission", "Desk Rejected Submission"]
stats = {cat: 0 for cat in categories}
for p in cleaned_papers:
    v = p.get("venue", "") or ""
    for cat in categories:
        if cat in v:
            stats[cat] += 1
            break # 匹配到一个状态即可
print("\n2c. 论文状态分类统计:")
for k, v in stats.items():
    print(f"  - {k}: {v}篇")
print(f"  - 校验总和: {sum(stats.values())}篇 (应接近总抓取数)")

# =========================
# 3. 评审与决策获取 (Task 3a-3c)
# =========================
# 文档要求只对前 100 篇提取 Review 减小开销
# =========================
# 增强型网络请求配置
# =========================
# 1. 创建一个持久的 Session 会话，复用底层连接
session = requests.Session()
session.headers.update(headers)

# 2. 定义一个带自动重试机制的请求函数
def fetch_with_retry(url, params, max_retries=3):
    for attempt in range(max_retries):
        try:
            # 加入 timeout 防止一直卡死
            response = session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response
            else:
                # 如果遇到 429 等状态码，多等一会儿
                time.sleep(1)
        except requests.exceptions.RequestException as e:
            # 捕获 SSLError 等网络异常
            if attempt == max_retries - 1:
                print(f"\n跳过某条记录，请求失败: {e}")
            else:
                # 遇到封锁或波动，休息久一点再重试 (比如 2秒)
                time.sleep(2)
    return None

# =========================
# 3. 评审与决策获取 (修改后的 Task 3a-3c)
# =========================
papers_subset = cleaned_papers[:100]

print("\n3a. 正在抓取前100篇论文的审稿意见 (Official Review)...")
for p in tqdm(papers_subset, desc="Official Reviews"):
    num = p.get("number")
    if not num: continue
    
    rev_params = {"invitation": f"{domain}/Submission{num}/-/Official_Review"}
    # 使用刚才封装的带重试机制的函数替换 requests.get
    rev_res = fetch_with_retry(api_url, params=rev_params)
    
    p["reviews"] = []
    if rev_res:
        notes = rev_res.json().get("notes", [])
        for n in notes:
            nc = n.get("content", {})
            p["reviews"].append({
                "soundness": extract_number(get_val(nc, "soundness")),
                "presentation": extract_number(get_val(nc, "presentation")),
                "contribution": extract_number(get_val(nc, "contribution")),
                "rating": extract_number(get_val(nc, "rating")),
                "confidence": extract_number(get_val(nc, "confidence"))
            })
    time.sleep(0.5)

# 保存任务 3a 的中间结果
with open("paper_info_cleaned_reviews.json", "w", encoding="utf-8") as f:
    json.dump(papers_subset, f, indent=2, ensure_ascii=False)


print("\n3b. 正在抓取元评审与最终决定 (Meta Review & Decision)...")
for p in tqdm(papers_subset, desc="Meta & Decision"):
    num = p.get("number")
    if not num: continue
    
    # Meta Review (使用重试函数)
    meta_params = {"invitation": f"{domain}/Submission{num}/-/Meta_Review"}
    meta_res = fetch_with_retry(api_url, params=meta_params)
    if meta_res:
        m_notes = meta_res.json().get("notes", [])
        if m_notes:
            mc = m_notes[0].get("content", {})
            p["meta_review"] = {
                "summary": get_val(mc, "summary"),
                "reviewer_concerns": get_val(mc, "reviewer_concerns"),
                "reviewer_scores": get_val(mc, "reviewer_scores")
            }
    
    # Decision (使用重试函数)
    dec_params = {"invitation": f"{domain}/Submission{num}/-/Decision"}
    dec_res = fetch_with_retry(api_url, params=dec_params)
    if dec_res:
        d_notes = dec_res.json().get("notes", [])
        if d_notes:
            p["decision"] = get_val(d_notes[0].get("content", {}), "decision")
    
    time.sleep(0.5)

# 保存任务 3b 最终结果
with open("paper_info_cleaned_final.json", "w", encoding="utf-8") as f:
    json.dump(papers_subset, f, indent=2, ensure_ascii=False)

    
# 3c. 数据分析探索
print("\n--- 3c. 分析报告 ---")
total_acc, total_rej = 0, 0
high_rej, low_acc = 0, 0
high_rej_w, low_acc_w = 0, 0

for p in papers_subset:
    dec = p.get("decision", "") or ""
    is_acc = "Accept" in dec and "Conditional" not in dec
    is_rej = "Reject" in dec and "Desk" not in dec
    
    if is_acc: total_acc += 1
    if is_rej: total_rej += 1
    
    revs = p.get("reviews", [])
    if not revs or not dec: continue
    
    ratings = [r['rating'] for r in revs if r['rating'] > 0]
    confs = [r['confidence'] for r in revs if r['confidence'] > 0]
    
    if ratings:
        avg = sum(ratings) / len(ratings)
        # 审稿人均分 > 5 但被拒稿
        if avg > 5 and is_rej: high_rej += 1
        # 审稿人均分 < 5 但被接收
        if avg < 5 and is_acc: low_acc += 1
        
        # 置信度加权处理
        if sum(confs) > 0:
            w_avg = sum(r * c for r, c in zip(ratings, confs)) / sum(confs)
            if w_avg > 5 and is_rej: high_rej_w += 1
            if w_avg < 5 and is_acc: low_acc_w += 1

print(f"被接收论文(不含Conditional): {total_acc} 篇")
print(f"被拒稿论文(不含Desk/Withdrawn): {total_rej} 篇")
print(f"均分>5 但最终被拒稿的论文: {high_rej} 篇")
print(f"均分<5 但最终被接收的论文: {low_acc} 篇")
print(f"加权均分>5 但最终被拒稿的论文: {high_rej_w} 篇")
print(f"加权均分<5 但最终被接收的论文: {low_acc_w} 篇")

# =========================
# 4. (选做) 存储关系型数据库
# =========================
print("\n--- 4. (选做) SQLite 数据入库 ---")
conn = sqlite3.connect('iclr_papers.db')
cursor = conn.cursor()

# 创建简化的数据表模式
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Papers (
        number INTEGER PRIMARY KEY,
        title TEXT,
        authors TEXT,
        venue TEXT,
        decision TEXT
    )
''')
# 清空旧数据防重复
cursor.execute('DELETE FROM Papers') 

for p in papers_subset:
    # 将列表处理为逗号分隔的字符串
    authors_str = ", ".join(p.get("authors", [])) if p.get("authors") else ""
    cursor.execute('''
        INSERT INTO Papers (number, title, authors, venue, decision)
        VALUES (?, ?, ?, ?, ?)
    ''', (p.get("number"), p.get("title"), authors_str, p.get("venue"), p.get("decision")))

conn.commit()

# 可视化前3行数据
print("数据库前3行记录：")
cursor.execute('SELECT number, title, decision FROM Papers LIMIT 3')
for row in cursor.fetchall():
    print(row)

conn.close()
print("\n所有任务执行完毕！")