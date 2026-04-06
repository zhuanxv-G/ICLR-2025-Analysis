# ICLR 2025 Paper Scraper & Analysis

## 📖 项目简介
本项目旨在自动化获取 AI 顶级会议 **ICLR 2025** 在 OpenReview 平台上的公开论文数据，并利用 Python 进行数据清洗与探索性分析（EDA）。通过对评审得分、接收状态及文本信息的挖掘，直观展示当前深度学习领域的前沿研究趋势。

## ✨ 核心亮点
* **自动化数据采集**：编写 Python 脚本定向抓取 OpenReview 平台上的论文元数据（标题、摘要、评审得分等），并处理了网页的反爬/动态加载机制。
* **数据清洗与结构化**：将非结构化的网页文本转化为结构化的 Pandas DataFrame，处理缺失值与异常数据。
* **可视化分析全链路**：在 Jupyter Notebook (`run.ipynb`) 中完成了数据探索，绘制了得分分布图、热点词云等直观图表。

## 🛠️ 技术栈
* **编程语言**：Python 3.x
* **数据抓取**：`requests` / `BeautifulSoup` 【如果你用了 Selenium，改成 Selenium】
* **数据处理与分析**：`Pandas`, `NumPy`
* **数据可视化**：`Matplotlib`, `Seaborn`

## 🚀 快速开始
如果你想在本地运行本项目，请按照以下步骤操作：

1. **克隆仓库**：
   ```bash
   git clone [https://github.com/zhuanxv-G/ICLR-2025-Analysis.git](https://github.com/zhuanxv-G/ICLR-2025-Analysis.git)
