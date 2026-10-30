# -*- coding: utf-8 -*-
# ==============================================================================
# 软件名称: 交通应急智能体软件 (TrafficAgent)
# 版本号: V6.0_Enterprise
# 开发作者: 章溥文
# 核心说明: 本系统基于 DeepSeek 大模型，实现城市交通拥堵的应急决策生成、
#           本地仿真数据降级、隐私脱敏以及多格式报告导出。
# ==============================================================================
import os
import re
import time
import json
import logging
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from openai import OpenAI
from duckduckgo_search import DDGS

# 全局常量定义
APP_VERSION = "V6.0_Enterprise"
APP_TITLE = f"交通应急智能体 {APP_VERSION}"
REPORTS_DIR = "reports"
LOGS_DIR = "logs"
CONFIG_FILE = "config.json"

# 确保必要的系统目录存在
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# ==============================================================================
# 海量本地仿真路况数据库 (Mock Data)
# 作用：当由于网络异常导致外部搜索接口超时时，系统自动降级调用此本地库，
#      确保软件在任何极端网络环境下都能输出专业的应急响应模板。
# ==============================================================================
LOCAL_TRAFFIC_DB = {
    "北京": {
        "东二环": {
            "morning_peak": "【本地仿真数据】当前状态：东直门桥至建国门桥南向北方向，受早高峰叠加影响。数据详情：平均车速15km/h，排队长度约4.5公里，拥堵指数8.2。趋势预测：预计恢复时间1.5小时。",
            "evening_peak": "【本地仿真数据】当前状态：广渠门桥至东直门桥北向南方向，车流量极度饱和。数据详情：平均车速12km/h，排队长度约6公里。",
            "accident": "【本地仿真数据】当前状态：左安门桥发生两车追尾。数据详情：占用左侧1条车道，排队长度约3公里，平均车速10km/h。",
        },
        "西二环": {
            "morning_peak": "【本地仿真数据】当前状态：复兴门桥至西直门桥南向北，常规拥堵。数据详情：平均车速20km/h，排队长度约3公里。",
            "evening_peak": "【本地仿真数据】当前状态：西直门桥至复兴门桥北向南，车流密集。",
            "accident": "【本地仿真数据】当前状态：月坛桥附近发生车辆抛锚。数据详情：占用应急车道，导致后方车辆缓行。",
        },
    },
    "上海": {
        "延安高架": {
            "morning_peak": "【本地仿真数据】当前状态：虹桥枢纽至延安东路立交东向，早高峰严重拥堵。数据详情：平均车速18km/h，排队长度约5公里。",
            "evening_peak": "【本地仿真数据】当前状态：延安东路立交至虹桥枢纽西向，晚高峰车流饱和。数据详情：平均车速20km/h。",
            "accident": "【本地仿真数据】当前状态：江苏路下匝道口发生多车剐蹭。数据详情：占用右侧2条车道，排队长度约4公里。",
        },
        "南北高架": {
            "morning_peak": "【本地仿真数据】当前状态：共和新路立交至鲁班路立交南向，车流量极大。数据详情：平均车速15km/h，排队长度约7公里。",
            "accident": "【本地仿真数据】当前状态：天目中路立交发生车辆故障。数据详情：占用最右侧车道。",
        },
    },
    "广州": {
        "华南快速": {
            "morning_peak": "【本地仿真数据】当前状态：南向北方向番禺大桥至土华立交段，车流密集。数据详情：平均车速25km/h，排队长度约2公里。",
            "accident": "【本地仿真数据】当前状态：北行至黄埔大道出口处，发生三车追尾。数据详情：占用中间车道，排队长度约3.5公里。",
        },
        "环城高速": {
            "accident": "【本地仿真数据】当前状态：环城高速东行沙贝立交段，货车故障。数据详情：占用最右侧车道，后方排队约2.5公里。"
        },
    },
    "深圳": {
        "滨海大道": {
            "morning_peak": "【本地仿真数据】当前状态：滨海大道东行，受科技园早高峰潮汐车流影响。数据详情：平均车速20km/h，排队长度约4公里。",
            "accident": "【本地仿真数据】当前状态：桂庙隧道入口发生两车碰撞。数据详情：占用左侧车道，排队约1.5公里。",
        },
        "北环大道": {
            "accident": "【本地仿真数据】当前状态：北环大道西行南头立交段，大货车抛锚。数据详情：占用右侧两车道，造成严重拥堵。"
        },
    },
    "成都": {
        "天府大道": {
            "morning_peak": "【本地仿真数据】当前状态：天府大道北段进城方向，早高峰常规拥堵。数据详情：平均车速18km/h，排队约3.5公里。",
            "accident": "【本地仿真数据】当前状态：天府大道北段出城方向，发生车辆自燃。数据详情：临时交通管制，全线拥堵。",
        }
    },
}

# ==============================================================================
# 提示词模板引擎
# ==============================================================================
PROMPT_TEMPLATES = {
    "极简汇报版": """
你是一个国家级交通应急专家。请生成一份【极简汇报版】的报告。
【严格规范】：
1. 字数控制在300字以内，去除一切废话。
2. 格式必须包含：'一、事件定性'、'二、P0-P3等级判定'、'三、核心调度指令'。
3. 语言必须像军令一样简洁，直接说明派多少人、封哪条路。
""",
    "详细作战版": """
你是一个国家级交通应急专家。请生成一份【详细作战版】的报告。
【严格规范】：
1. 字数在800字以上，包含详细的推导过程。
2. 结构必须包含：
   - 一、事件全景摘要（含仿真数据分析）
   - 二、P0-P3分级响应矩阵（必须使用Markdown表格）
   - 三、周边路网绕行方案（必须分主辅路、近远端说明）
   - 四、医疗与救援力量调度建议（警力、消防、急救分布）
3. 必须使用极其专业的交通工程术语。
""",
    "英文国际版": """
You are a National Traffic Emergency Expert. Please generate an 【International Standard Report】 in English.
Requirements:
1. Include 'Event Summary', 'P0-P3 Level Response Matrix', and 'Evacuation & Dispatch SOP'.
2. You must use Markdown tables for the response matrix.
3. The tone should be highly professional and suited for international conferences.
""",
}


# ==============================================================================
# 基础设施模块类
# ==============================================================================
class LoggerManager:
    """
    日志管理器：负责初始化并返回全局的日志记录器。
    将运行状态同时输出到控制台和本地日志文件中，方便系统异常追踪。
    """

    @staticmethod
    def setup_logger():
        log_format = "%(asctime)s - [%(levelname)s] - %(message)s"
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(
                    os.path.join(LOGS_DIR, "agent_run.log"), encoding="utf-8"
                ),
                logging.StreamHandler(),
            ],
        )
        return logging.getLogger("TrafficAgentV6")


logger = LoggerManager.setup_logger()


class ConfigManager:
    """
    配置管理器：负责读取和保存系统的 JSON 配置文件。
    实现代码逻辑与敏感信息（如 API Key）的解耦。
    """

    @staticmethod
    def load_config():
        """读取配置文件，若不存在则返回默认配置字典"""
        default_config = {
            "api_key": "",
            "default_city": "上海",
            "default_mode": "详细作战版",
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取配置失败: {e}")
                return default_config
        return default_config

    @staticmethod
    def save_config(config_dict):
        """将配置字典持久化写入 JSON 文件"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False


# 初始化全局配置与 API Key
CURRENT_CONFIG = ConfigManager.load_config()
ENV_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-xxxxxxxxxxxx")
DEEPSEEK_API_KEY = ENV_KEY if ENV_KEY else CURRENT_CONFIG.get("api_key", "")


# ==============================================================================
# 核心业务功能类
# ==============================================================================
class DataProcessor:
    """
    数据处理类：负责对生成的应急报告进行正则脱敏与文本清洗。
    保障系统输出内容符合信息安全规范。
    """

    @staticmethod
    def mask_privacy(text):
        """正则脱敏：过滤文本中的车牌号（如京A12345）和手机号"""
        if not text:
            return text
        # 匹配中国大陆车牌
        plate_pattern = r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领A-Z]{1}[A-Z]{1}[A-Z0-9]{4}[A-Z0-9挂学警港澳]{1}"
        text = re.sub(plate_pattern, "【隐私保护：车牌已脱敏】", text)
        # 匹配手机号
        phone_pattern = r"1[3-9]\d{9}"
        text = re.sub(phone_pattern, "【隐私保护：手机号已脱敏】", text)
        return text

    @staticmethod
    def clean_text(text):
        """文本清洗：去除多余的连续换行符，并清理首尾空格"""
        if not text:
            return text
        # 将三个以上的连续换行替换为两个，保持排版紧凑
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class WebSearcher:
    """
    联网搜索类：负责调用第三方 DuckDuckGo 引擎进行外挂抓取。
    体现系统的感知层扩展能力。
    """

    @staticmethod
    def search_traffic(query):
        logger.info(f"🌐 [感知层外挂] 正在全网搜索：{query}")
        try:
            # 限制返回结果数量和超时时间
            results = DDGS().text(f"{query} 实时路况", max_results=3, region="cn-zh")
            if not results:
                return None

            search_text = ""
            for r in results:
                search_text += f"- {r['title']}：{r['body']}\n"
            return search_text
        except Exception as e:
            logger.warning(f"⚠️ 搜索接口异常或超时：{e}")
            return None


class ReportExporter:
    """
    报告导出模块：支持将 Markdown 格式的报告转化为纯文本 (.txt) 并附带字数统计。
    体现系统的数据持久化与多格式支持能力。
    """

    @staticmethod
    def export_to_txt(md_content, city, road):
        logger.info("📄 [导出层] 正在执行文本导出任务...")
        try:
            # 使用正则去除 Markdown 标签符号
            txt_content = re.sub(r"[#*`>|-]", "", md_content)
            word_count = len(txt_content)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"导出_{city}_{road}_{timestamp}.txt"
            filepath = os.path.join(REPORTS_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"【报告字数统计】: {word_count} 字\n\n")
                f.write(txt_content)

            logger.info(f"✅ 成功导出纯文本报告: {filename}")
            return True, filepath
        except Exception as e:
            logger.error(f"❌ 导出失败: {e}")
            return False, str(e)


# ==============================================================================
# AI 大模型调用引擎
# ==============================================================================
class DeepSeekEngine:
    """
    大模型调度引擎：封装 DeepSeek API 接口。
    内置指数退避重试机制，保障系统在弱网环境下的请求稳定性。
    """

    def __init__(self):
        if not DEEPSEEK_API_KEY:
            raise ValueError("API Key 未配置，请在系统设置中填写。")
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-chat"

    def generate(self, system_prompt, user_prompt, max_retries=3):
        """执行大模型请求，失败时自动重试"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2500,
                )
                result = response.choices[0].message.content
                if result:
                    return result
                else:
                    raise ValueError("大模型返回空内容")
            except Exception as e:
                logger.warning(f"⚠️ 第 {attempt+1} 次请求失败：{e}")
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # 指数退避
                else:
                    logger.error("❌ 达到最大重试次数，生成失败。")
                    return f"生成失败，请检查网络或 API 余额。详细报错：{e}"


# ==============================================================================
# GUI 图形用户界面模块
# ==============================================================================
class TrafficAgentGUI:
    def __init__(self, root):
        """初始化 GUI 窗口与核心组件"""
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x850")
        self.root.configure(padx=15, pady=15)

        # 构建顶部选项卡
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 选项卡1：实时生成
        self.tab_generate = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_generate, text="🚀 实时应急生成")
        self.setup_generate_tab()

        # 选项卡2：历史报告
        self.tab_history = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_history, text="📁 历史报告归档")
        self.setup_history_tab()

        # 选项卡3：系统配置
        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="⚙️ 系统配置")
        self.setup_settings_tab()

        # 加载历史记录
        self.load_history_reports()

    def setup_generate_tab(self):
        """搭建实时生成页面的 UI 布局"""
        frame_top = tk.Frame(self.tab_generate)
        frame_top.pack(fill=tk.X, pady=(10, 10))

        # 城市选择下拉框
        tk.Label(frame_top, text="查询城市:", font=("微软雅黑", 11)).grid(
            row=0, column=0, padx=5, pady=5
        )
        self.city_combo = ttk.Combobox(
            frame_top,
            values=list(LOCAL_TRAFFIC_DB.keys()),
            font=("微软雅黑", 11),
            width=10,
            state="readonly",
        )
        self.city_combo.set(CURRENT_CONFIG.get("default_city", "上海"))
        self.city_combo.grid(row=0, column=1, padx=5, pady=5)

        # 道路输入框
        tk.Label(frame_top, text="道路名称:", font=("微软雅黑", 11)).grid(
            row=0, column=2, padx=5, pady=5
        )
        self.road_entry = tk.Entry(frame_top, font=("微软雅黑", 11), width=18)
        self.road_entry.insert(0, "延安高架")
        self.road_entry.grid(row=0, column=3, padx=5, pady=5)

        # 模式选择下拉框
        tk.Label(frame_top, text="生成模式:", font=("微软雅黑", 11)).grid(
            row=0, column=4, padx=5, pady=5
        )
        self.mode_combo = ttk.Combobox(
            frame_top,
            values=list(PROMPT_TEMPLATES.keys()),
            font=("微软雅黑", 11),
            width=15,
            state="readonly",
        )
        self.mode_combo.set(CURRENT_CONFIG.get("default_mode", "详细作战版"))
        self.mode_combo.grid(row=0, column=5, padx=5, pady=5)

        # 功能按钮组
        self.btn_gen = tk.Button(
            frame_top,
            text="🚀 立即生成",
            font=("微软雅黑", 10, "bold"),
            bg="#0078D7",
            fg="white",
            width=12,
            command=self.start_generation,
        )
        self.btn_gen.grid(row=0, column=6, padx=10, pady=5)

        self.btn_export = tk.Button(
            frame_top,
            text="📄 导出纯文本",
            font=("微软雅黑", 10, "bold"),
            bg="#28a745",
            fg="white",
            width=12,
            command=self.start_export,
        )
        self.btn_export.grid(row=0, column=7, padx=5, pady=5)

        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("系统就绪。请点击生成。")
        tk.Label(
            self.tab_generate,
            textvariable=self.status_var,
            font=("微软雅黑", 10),
            fg="#0078D7",
            anchor="w",
        ).pack(fill=tk.X)

        # 文本显示大框
        self.text_area = scrolledtext.ScrolledText(
            self.tab_generate,
            font=("Consolas", 11),
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
        )
        self.text_area.pack(fill=tk.BOTH, expand=True, pady=10)

    def setup_history_tab(self):
        """搭建历史归档页面的 UI 布局"""
        frame_left = tk.Frame(self.tab_history, width=300)
        frame_left.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        tk.Label(frame_left, text="历史报告列表:", font=("微软雅黑", 11)).pack(
            anchor="w"
        )
        self.file_list = tk.Listbox(
            frame_left, font=("微软雅黑", 10), width=40, height=30
        )
        self.file_list.pack(fill=tk.BOTH, expand=True, pady=5)
        self.file_list.bind("<<ListboxSelect>>", self.on_file_select)

        frame_right = tk.Frame(self.tab_history)
        frame_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(frame_right, text="报告内容预览:", font=("微软雅黑", 11)).pack(
            anchor="w"
        )
        self.preview_area = scrolledtext.ScrolledText(
            frame_right, font=("Consolas", 11), wrap=tk.WORD, bg="#252526", fg="#cccccc"
        )
        self.preview_area.pack(fill=tk.BOTH, expand=True, pady=5)

    def setup_settings_tab(self):
        """搭建系统配置页面的 UI 布局"""
        frame_conf = tk.Frame(self.tab_settings)
        frame_conf.pack(fill=tk.X, pady=30, padx=30)

        tk.Label(frame_conf, text="DeepSeek API Key:", font=("微软雅黑", 12)).grid(
            row=0, column=0, sticky="w", pady=10
        )
        self.api_entry = tk.Entry(frame_conf, font=("微软雅黑", 12), width=60, show="*")
        self.api_entry.insert(0, CURRENT_CONFIG.get("api_key", DEEPSEEK_API_KEY))
        self.api_entry.grid(row=0, column=1, padx=10, pady=10)

        btn_save = tk.Button(
            frame_conf,
            text="💾 保存系统配置",
            font=("微软雅黑", 11),
            bg="#17a2b8",
            fg="white",
            width=15,
            command=self.save_system_config,
        )
        btn_save.grid(row=1, column=0, columnspan=2, pady=20)

    def save_system_config(self):
        """保存用户在界面中填写的配置"""
        new_key = self.api_entry.get().strip()
        CURRENT_CONFIG["api_key"] = new_key
        if ConfigManager.save_config(CURRENT_CONFIG):
            messagebox.showinfo("成功", "配置已保存。请重新启动软件生效。")
            logger.info("用户更新了系统 API Key 配置。")

    def load_history_reports(self):
        """扫描并加载 reports 文件夹下的所有 Markdown 文件"""
        self.file_list.delete(0, tk.END)
        if not os.path.exists(REPORTS_DIR):
            return
        files = [f for f in os.listdir(REPORTS_DIR) if f.endswith(".md")]
        files.sort(reverse=True)  # 按时间倒序排列
        for f in files:
            self.file_list.insert(tk.END, f)

    def on_file_select(self, event):
        """点击列表中的文件时，在右侧展示内容"""
        selection = self.file_list.curselection()
        if selection:
            filename = self.file_list.get(selection[0])
            filepath = os.path.join(REPORTS_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    self.preview_area.delete(1.0, tk.END)
                    self.preview_area.insert(tk.END, f.read())
            except Exception as e:
                logger.error(f"预览文件失败: {e}")

    def update_status(self, msg):
        """更新底部状态栏并记录日志"""
        self.status_var.set(msg)
        logger.info(msg)

    def start_generation(self):
        """触发大模型生成任务"""
        city = self.city_combo.get()
        road = self.road_entry.get().strip()
        mode = self.mode_combo.get()

        if not road:
            messagebox.showwarning("警告", "道路名称不能为空！")
            return

        self.btn_gen.config(state=tk.DISABLED, text="⏳ 生成中...")
        self.text_area.delete(1.0, tk.END)

        # 开启子线程执行任务，防止 GUI 界面卡死
        threading.Thread(
            target=self.run_task, args=(city, road, mode), daemon=True
        ).start()

    def start_export(self):
        """触发报告导出任务"""
        current_text = self.text_area.get("1.0", tk.END).strip()
        if not current_text:
            messagebox.showwarning("提示", "当前没有内容可以导出！")
            return

        city = self.city_combo.get()
        road = self.road_entry.get().strip()

        success, msg = ReportExporter.export_to_txt(current_text, city, road)
        if success:
            messagebox.showinfo("成功", f"导出成功！\n已保存至 reports 文件夹。")
        else:
            messagebox.showerror("失败", f"导出失败：{msg}")

    def run_task(self, city, road, mode):
        """后台任务核心逻辑：获取数据 -> 大模型决策 -> 脱敏 -> 归档"""
        full_name = f"{city}{road}"
        self.update_status(f"正在处理：{full_name}...")

        # 1. 尝试联网搜索，若失败则降级
        real_data = WebSearcher.search_traffic(full_name)
        if real_data:
            data_context = real_data
            self.update_status("✅ 成功获取互联网实时数据。")
        else:
            self.update_status("🔄 网络超时，触发降级机制，调取本地仿真数据库。")
            city_data = LOCAL_TRAFFIC_DB.get(city, {})
            road_data = city_data.get(road)
            if isinstance(road_data, dict):
                data_context = list(road_data.values())[0]
            else:
                data_context = f"【通用模板】{full_name} 发生突发拥堵，请生成应急预案。"

        # 2. 调用大模型
        try:
            engine = DeepSeekEngine()
            prompt = PROMPT_TEMPLATES.get(mode, PROMPT_TEMPLATES["详细作战版"])
            self.update_status("✍️ 正在请求大模型生成决策报告...")

            raw_report = engine.generate(
                prompt, f"生成关于【{full_name}】的报告：\n\n{data_context}"
            )

            # 3. 脱敏处理与内容清洗
            safe_report = DataProcessor.mask_privacy(raw_report)
            final_report = DataProcessor.clean_text(safe_report)

            # 4. 回显与文件保存
            self.text_area.insert(tk.END, final_report)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"报告_{full_name}_{mode}_{timestamp}.md"
            filepath = os.path.join(REPORTS_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(final_report)

            self.update_status(f"✅ 报告生成成功！已保存至 {filename}")
            self.load_history_reports()

        except Exception as e:
            self.text_area.insert(tk.END, f"系统发生异常：{e}")
            self.update_status("❌ 生成失败。")

        finally:
            # 恢复按钮状态
            self.btn_gen.config(state=tk.NORMAL, text="🚀 立即生成")


# ==============================================================================
# 程序主入口
# ==============================================================================
if __name__ == "__main__":
    logger.info("====================================")
    logger.info(f"软件启动: {APP_VERSION}")
    logger.info("====================================")

    root = tk.Tk()
    app = TrafficAgentGUI(root)
    root.mainloop()
