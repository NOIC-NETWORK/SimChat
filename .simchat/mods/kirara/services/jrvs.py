# jrvs.py
# Kirara JRVS (Joint Ratiocination Visual System), An Enhanced Generative AI Engine
# Author: Barry Molynton(Founder, Chairman and CTO of TeleVideo Inc.)
# Version: 3.1.3 Alpha (Project Dartmouth)
# 版本号命名规范： <Kirara版本号>.<JRVS版本号>.<记忆库版本号>
"""

接下来的事情：
1.加入ReAct循环
2.配置专门的EcoStealth架构，在低能耗模式下采用GPU+CPU混合推理，从而减少显存占用。
3.配置Skills。包括：阅读、编辑、终端操作、截图识别、网页搜索。

"""
# 导入系统依赖
import os
import sys
import subprocess
import json
import re
import asyncio
import threading
import time
import datetime

# 取消 sentence-transformers / HF Hub 的自动更新检查：
# 本地已缓存 all-MiniLM-L6-v2 时纯离线加载，避免每次启动向 HF 镜像查询并拉取新版本；
# 仅当缓存不存在时才联网（首次下载），保证全新环境仍可初始化。
_HF_HOME = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
_HF_HUB_CACHE = os.environ.get("HUGGINGFACE_HUB_CACHE") or os.path.join(_HF_HOME, "hub")
_EMBED_CACHE_DIR = os.path.join(_HF_HUB_CACHE, "models--sentence-transformers--all-MiniLM-L6-v2")
if os.path.isdir(_EMBED_CACHE_DIR):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    print("[System] all-MiniLM-L6-v2 已有本地缓存，已关闭自动更新（离线加载）")

# 安全导入 chromadb
CHROMADB_AVAILABLE = False
try:
    import chromadb
    CHROMADB_AVAILABLE = True
    print("[System] chromadb 导入成功")
except ImportError:
    CHROMADB_AVAILABLE = False
    print("[警告] chromadb 未安装，将使用简化版记忆系统")

# 安全导入 websockets
WEBSOCKETS_AVAILABLE = False
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
    print("[System] websockets 导入成功")
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[警告] websockets 未安装，WebSocket服务将不可用")

# 安全导入 anime_style_converter (暂时注释掉)
ANIME_CONVERTER_AVAILABLE = False
try:
    # from anime_style_converter import anime_converter, AnimePersonality
    # ANIME_CONVERTER_AVAILABLE = True
    # print("[System] anime_style_converter 导入成功")
    raise ImportError("暂时禁用")
except ImportError:
    ANIME_CONVERTER_AVAILABLE = False
    AnimePersonality = None
    print("[警告] anime_style_converter 未安装，将使用默认回复风格")

# 初始化 sentence_transformers 相关变量
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
    print("[System] sentence_transformers 导入成功")
except ImportError as e:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    print(f"[警告] sentence_transformers 导入失败: {str(e)}")
    print("[警告] 原因可能是torch DLL依赖缺失，将使用简化版记忆检索")
    print("[提示] 尝试修复：pip install torch --force-reinstall 或使用--target安装到项目目录")

# 尝试使用 ollama 替代 llama-cli.exe
OLLAMA_AVAILABLE = False
try:
    import ollama
    from ollama import Client
    OLLAMA_AVAILABLE = True
    print("[System] ollama 导入成功，可以使用 CUDA 推理")
except ImportError:
    OLLAMA_AVAILABLE = False
    print("[警告] ollama 未安装，将尝试使用 llama-cli.exe")
except TypeError as e:
    OLLAMA_AVAILABLE = False
    print(f"[警告] ollama 依赖兼容性问题: {e}")
    print("[提示] 尝试修复: pip install 'exceptiongroup<1.2' 或 'anyio<4'")
except Exception as e:
    OLLAMA_AVAILABLE = False
    print(f"[警告] ollama 导入失败: {type(e).__name__}: {e}")

# 使用 llama-cli.exe 作为备选
LLAMA_CLI_PATH = r"E:\virtuaos\apps\kirara\llama.cpp\build\bin\Release\llama-cli.exe"
LLAMA_AVAILABLE = os.path.exists(LLAMA_CLI_PATH)
if not LLAMA_AVAILABLE and not OLLAMA_AVAILABLE:
    print(f"[警告] llama-cli.exe 不存在于路径: {LLAMA_CLI_PATH}")
    print("[警告] 无法使用 LLM 功能，将启用模拟模式")

# 个性化知识库（knowledge_base.md 权威档案检索，抑制用户事实类幻觉）
try:
    from knowledge_base import KnowledgeBase
    KNOWLEDGE_BASE_AVAILABLE = True
    print("[System] knowledge_base 模块导入成功")
except Exception as _kb_import_error:
    KNOWLEDGE_BASE_AVAILABLE = False
    KnowledgeBase = None
    print(f"[警告] knowledge_base 模块加载失败: {_kb_import_error}")

def check_environ():
    # 检查 ollama 服务是否运行
    try:
        # 尝试执行一个简单的 ollama 命令来检查服务状态
        result = subprocess.run("ollama list", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        if result.returncode == 0:
            print("[System] ollama 服务已运行")
        else:
            print("[警告] ollama 服务未运行")
    except Exception as e:
        print(f"[警告] 检查 ollama 服务时出错: {e}")


class ModelDeploymentChecker:
    def __init__(self):
        self.model_status = {}
        self.deploy_errors = []
        self.ollama_available = False
        self.ollama_service_running = False

    def check_ollama_installation(self):
        try:
            result = subprocess.run("ollama --version", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            if result.returncode == 0:
                self.ollama_available = True
                version_info = result.stdout.strip()
                print(f"[Deploy] Ollama 已安装: {version_info}")
                return True, f"Ollama 已安装: {version_info}"
            else:
                self.ollama_available = False
                self.deploy_errors.append("Ollama 未安装")
                print("[Deploy] ERROR: Ollama 未安装")
                return False, "Ollama 未安装"
        except FileNotFoundError:
            self.ollama_available = False
            self.deploy_errors.append("Ollama 命令未找到")
            print("[Deploy] ERROR: Ollama 命令未找到，请安装 Ollama")
            return False, "Ollama 命令未找到"
        except Exception as e:
            self.ollama_available = False
            self.deploy_errors.append(f"检查 Ollama 时出错: {e}")
            print(f"[Deploy] ERROR: 检查 Ollama 时出错: {e}")
            return False, f"检查 Ollama 时出错: {e}"

    def check_ollama_service(self):
        if not self.ollama_available:
            return False, "Ollama 不可用"
        
        try:
            result = subprocess.run("ollama list", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            if result.returncode == 0:
                self.ollama_service_running = True
                print("[Deploy] Ollama 服务已运行")
                return True, "Ollama 服务已运行"
            else:
                self.ollama_service_running = False
                self.deploy_errors.append("Ollama 服务未运行")
                print("[Deploy] WARNING: Ollama 服务未运行")
                return False, "Ollama 服务未运行"
        except Exception as e:
            self.ollama_service_running = False
            self.deploy_errors.append(f"检查 Ollama 服务时出错: {e}")
            print(f"[Deploy] ERROR: 检查 Ollama 服务时出错: {e}")
            return False, f"检查 Ollama 服务时出错: {e}"

    def check_model_file(self, model_key):
        if model_key not in MODELS:
            return False, f"未知模型: {model_key}"

        model_config = MODELS[model_key]

        # Hub 模型（如 televideo-ai/JRVS-7B-1.2.2）无需本地 gguf 文件，跳过文件检查
        if model_config.get("source") == "hub":
            self.model_status[model_key] = {
                "file_exists": True,
                "file_size_mb": None,
                "ollama_model": model_config["ollama_model"],
                "status": "file_ready",
                "source": "hub"
            }
            print(f"[Deploy] Hub 模型，无需本地文件: {model_key} ({model_config['ollama_model']})")
            return True, f"Hub 模型（{model_config['ollama_model']}），通过 ollama pull 获取"

        model_path = model_config["path"]

        try:
            if os.path.exists(model_path):
                file_size = os.path.getsize(model_path) / (1024 * 1024)
                self.model_status[model_key] = {
                    "file_exists": True,
                    "file_size_mb": round(file_size, 2),
                    "ollama_model": model_config["ollama_model"],
                    "status": "file_ready",
                    "source": "local"
                }
                print(f"[Deploy] 模型文件存在: {model_key} ({round(file_size, 2)} MB)")
                return True, f"模型文件存在 ({round(file_size, 2)} MB)"
            else:
                self.model_status[model_key] = {
                    "file_exists": False,
                    "ollama_model": model_config["ollama_model"],
                    "status": "file_missing",
                    "source": "local"
                }
                self.deploy_errors.append(f"模型文件不存在: {model_path}")
                print(f"[Deploy] ERROR: 模型文件不存在: {model_path}")
                return False, f"模型文件不存在: {model_path}"
        except Exception as e:
            self.model_status[model_key] = {
                "file_exists": False,
                "ollama_model": model_config["ollama_model"],
                "status": "error",
                "source": "local"
            }
            self.deploy_errors.append(f"检查模型文件时出错: {e}")
            print(f"[Deploy] ERROR: 检查模型文件时出错: {e}")
            return False, f"检查模型文件时出错: {e}"

    def check_ollama_model(self, model_key):
        if not self.ollama_service_running:
            return False, "Ollama 服务未运行"
        
        if model_key not in MODELS:
            return False, f"未知模型: {model_key}"
        
        model_config = MODELS[model_key]
        ollama_model_name = model_config["ollama_model"]
        
        try:
            result = subprocess.run("ollama list", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
            if result.returncode == 0:
                model_list = result.stdout
                if ollama_model_name in model_list:
                    self.model_status[model_key]["ollama_registered"] = True
                    self.model_status[model_key]["status"] = "ready"
                    print(f"[Deploy] Ollama 模型已注册: {ollama_model_name}")
                    return True, f"Ollama 模型已注册: {ollama_model_name}"
                else:
                    self.model_status[model_key]["ollama_registered"] = False
                    self.model_status[model_key]["status"] = "needs_deploy"
                    print(f"[Deploy] Ollama 模型未注册: {ollama_model_name}")
                    return False, f"Ollama 模型未注册: {ollama_model_name}"
            else:
                self.deploy_errors.append("获取模型列表失败")
                print(f"[Deploy] ERROR: 获取模型列表失败")
                return False, "获取模型列表失败"
        except Exception as e:
            self.deploy_errors.append(f"检查 Ollama 模型时出错: {e}")
            print(f"[Deploy] ERROR: 检查 Ollama 模型时出错: {e}")
            return False, f"检查 Ollama 模型时出错: {e}"

    def deploy_ollama_model(self, model_key):
        if model_key not in MODELS:
            return False, f"未知模型: {model_key}"

        if not self.ollama_service_running:
            return False, "Ollama 服务未运行"

        model_config = MODELS[model_key]
        ollama_model_name = model_config["ollama_model"]

        # Hub 模型：直接 ollama pull，无需本地 gguf 或 modelfile
        if model_config.get("source") == "hub":
            print(f"[Deploy] 正在从 Ollama Hub 拉取模型: {ollama_model_name}")
            result = subprocess.run(
                f"ollama pull {ollama_model_name}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=600
            )
            if result.returncode == 0:
                self.model_status[model_key]["ollama_registered"] = True
                self.model_status[model_key]["status"] = "ready"
                print(f"[Deploy] OK: Hub 模型拉取成功: {ollama_model_name}")
                return True, f"Hub 模型拉取成功: {ollama_model_name}"
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                self.deploy_errors.append(f"拉取模型失败: {error_msg}")
                print(f"[Deploy] ERROR: 拉取模型失败: {error_msg}")
                return False, f"拉取模型失败: {error_msg}"

        # 本地 gguf 模型：通过 modelfile 创建
        model_path = model_config["path"]

        if not os.path.exists(model_path):
            return False, f"模型文件不存在: {model_path}"
        
        build_dir = os.path.join(APP_DIR, "build")
        temp_modelfile = os.path.join(build_dir, "modelfile-temp.txt")
        source_modelfile = os.path.join(build_dir, "modelfile.txt")
        
        try:
            if not os.path.exists(source_modelfile):
                print(f"[Deploy] ERROR: 源 modelfile 不存在: {source_modelfile}")
                return False, f"源 modelfile 不存在: {source_modelfile}"
            
            import shutil
            shutil.copy2(source_modelfile, temp_modelfile)
            
            with open(temp_modelfile, "r", encoding="utf-8") as f:
                content = f.read()

            # 通用替换：匹配 FROM 行的任意 gguf 路径，替换为当前模型路径
            import re as _re
            content = _re.sub(r'^FROM\s+.*$', f'FROM {model_path}', content, count=1, flags=_re.MULTILINE)

            with open(temp_modelfile, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"[Deploy] 正在创建 Ollama 模型: {ollama_model_name}")
            result = subprocess.run(
                f"ollama create {ollama_model_name} -f \"{temp_modelfile}\"",
                shell=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                os.remove(temp_modelfile)
                self.model_status[model_key]["ollama_registered"] = True
                self.model_status[model_key]["status"] = "ready"
                print(f"[Deploy] OK: Ollama 模型创建成功: {ollama_model_name}")
                return True, f"Ollama 模型创建成功: {ollama_model_name}"
            else:
                os.remove(temp_modelfile)
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                self.deploy_errors.append(f"创建模型失败: {error_msg}")
                print(f"[Deploy] ERROR: 创建模型失败: {error_msg}")
                return False, f"创建模型失败: {error_msg}"
        except Exception as e:
            if os.path.exists(temp_modelfile):
                os.remove(temp_modelfile)
            self.deploy_errors.append(f"部署模型时出错: {e}")
            print(f"[Deploy] ERROR: 部署模型时出错: {e}")
            return False, f"部署模型时出错: {e}"

    def run_full_check(self, auto_deploy=False):
        print("[Deploy] ========== 模型部署检测系统 ==========")
        
        results = {
            "ollama_installed": False,
            "ollama_service_running": False,
            "models": {}
        }
        
        results["ollama_installed"], msg = self.check_ollama_installation()
        if not results["ollama_installed"]:
            print("[Deploy] ========== 检测结束 ==========")
            return results
        
        results["ollama_service_running"], msg = self.check_ollama_service()
        
        for model_key in MODELS:
            print(f"[Deploy] --- 检查模型: {model_key} ---")
            file_ok, file_msg = self.check_model_file(model_key)
            results["models"][model_key] = {"file_ok": file_ok, "file_msg": file_msg}
            
            if file_ok and self.ollama_service_running:
                ollama_ok, ollama_msg = self.check_ollama_model(model_key)
                results["models"][model_key]["ollama_ok"] = ollama_ok
                results["models"][model_key]["ollama_msg"] = ollama_msg
                
                if not ollama_ok and auto_deploy:
                    print(f"[Deploy] 自动部署模型: {model_key}")
                    deploy_ok, deploy_msg = self.deploy_ollama_model(model_key)
                    results["models"][model_key]["deployed"] = deploy_ok
                    results["models"][model_key]["deploy_msg"] = deploy_msg
        
        print("[Deploy] ========== 检测结束 ==========")
        return results

    def get_summary(self):
        summary = []
        if not self.ollama_available:
            summary.append("❌ Ollama 未安装")
        else:
            summary.append("✅ Ollama 已安装")
        
        if not self.ollama_service_running:
            summary.append("❌ Ollama 服务未运行")
        else:
            summary.append("✅ Ollama 服务已运行")
        
        for model_key, status in self.model_status.items():
            if status.get("status") == "ready":
                summary.append(f"✅ 模型 {model_key}: 已就绪")
            elif status.get("status") == "file_ready":
                summary.append(f"⚠️ 模型 {model_key}: 文件存在，但未注册到 Ollama")
            elif status.get("status") == "file_missing":
                summary.append(f"❌ 模型 {model_key}: 文件缺失")
            else:
                summary.append(f"⚠️ 模型 {model_key}: {status.get('status', '未知状态')}")
        
        if self.deploy_errors:
            summary.append("\n错误详情:")
            for error in self.deploy_errors:
                summary.append(f"  - {error}")
        
        return "\n".join(summary)
# ==========================================
#              配置区 (Config)
# ==========================================
# 使用绝对路径，基于当前文件位置
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(SERVICE_DIR)

# 模型配置
# kiraraModelC: JRVS-7B-1.2.2 "Puff" (TeleVideo Inc. 自研 8B SFT+LoRA 模型，基于 Qwen3-8B)
#   - 从 Ollama Hub 拉取: ollama pull televideo-ai/JRVS-7B-1.2.2
#   - Q4_K_M 档约 4.9GB，8GB 显存可全层载入（37/37 层），无需 CPU/GPU 混合推理
#   - 双人设 SFT: system="JRVS" 或不传 → JRVS（称呼「先生」）；system="Kirara" → Kirara
#   - Qwen3 世代、enable_thinking=False 训练分布：Hub 模型模板自带空 think 段，直接回答
#   - 训练上下文 32768 tokens，qwen3 架构；Ollama 标签窗口 40K
MODELS = {
    "kiraraModelC": {
        "name": "JRVS-7B-1.2.2 (System 1)",
        "path": None,
        "ollama_model": "televideo-ai/JRVS-7B-1.2.2:latest",
        "source": "hub",
        "personality": "daily",
        "system": "System 1"
    },
    "kiraraModelO": {
        "name": "Kirara Expert (System 2)",
        "path": os.path.join(APP_DIR, "models", "qwen2.5-8b-instruct-q4_k_m.gguf"),
        "ollama_model": "kirara-expert",
        "source": "local",
        "personality": "expert",
        "system": "System 2"
    }
}

# 用户角色设定已移至 sysPrompt.txt 的 USER PROFILE 部分
# 此处不再硬编码，改为从记忆文件动态检索

# 默认模型
DEFAULT_MODEL = "kiraraModelC"
MODEL_PATH = MODELS[DEFAULT_MODEL]["path"]

CHROMA_PATH = os.path.join(APP_DIR, "memories", "kirara_memory")
EMBED_MODEL = 'all-MiniLM-L6-v2'

# 旧版 sysPrompt.txt 系统（llama3 时代长提示词），JRVS-7B-1.2.2 不再使用。
# JRVS-7B 为 SFT+LoRA 训练模型，人设通过 system prompt 关键词触发：
#   - 无 system prompt → 原生人设（JRVS，称呼「先生」，专业简洁）
#   - system="JRVS"    → JRVS 模式（同原生）
#   - system="Kirara"  → Kirara 模式（称呼「主人sama」，活泼女仆风）
# 1.2.2 基于 Qwen3-8B，Hub 模型模板已内置 enable_thinking=False 的空 think 段，
# 走 ollama.chat 即直接输出答案，无需（也不要）额外传 think 参数。
# sysPrompt.txt 保留作为 DeepThinkingEngine.polish 的备选上下文，不再注入推理 system 角色。
SYS_PROMPT_PATH = os.path.join(APP_DIR, "memories", "sysPrompt.txt")
try:
    SYSTEM_PROMPT = open(SYS_PROMPT_PATH, "r", encoding="utf-8").read()
    print(f"[System] sysPrompt.txt 已加载（仅供 DeepThinkingEngine 备选），长度: {len(SYSTEM_PROMPT)}")
except FileNotFoundError:
    print(f"[警告] 系统提示词文件不存在: {SYS_PROMPT_PATH}")
    SYSTEM_PROMPT = ""

# JRVS-7B 双人设模式（SFT 训练设定，通过 system prompt 切换）
# system="JRVS"  -> 称呼「先生」，专业、简洁、无颜文字（226 条训练样本）
# system="Kirara"-> 称呼「主人sama」，活泼甜美、颜文字、女仆风（228 条训练样本）
# native         -> 不注入 system prompt，使用模型原生人设（JRVS 为默认原生人格）
PERSONA_PROMPTS = {
    "native": {
        "label": "模型原生",
        "en_name": "Native",
        "icon": "🤖",
        "system": None,
        "description": "不注入人设提示词，使用模型原生人格（JRVS 默认为原生人设），兼容当前 sysPrompt.txt。"
    },
    "jrvs": {
        "label": "贾维斯",
        "en_name": "JRVS",
        "icon": "🎩",
        "system": "JRVS",
        "description": "JRVS 模式：称呼「先生」，专业、简洁、无颜文字。"
    },
    "kirara": {
        "label": "绮罗",
        "en_name": "Kirara",
        "icon": "🎀",
        "system": "Kirara",
        "description": "Kirara 模式：称呼「主人sama」，活泼甜美、颜文字、女仆风。"
    }
}
DEFAULT_PERSONA = "native"


def resolve_persona_system(persona_key):
    """根据人设 key 返回 SFT 对应的 system prompt；native/未知值返回 None。"""
    persona = PERSONA_PROMPTS.get(persona_key)
    if persona is None:
        print(f"[Persona] 未知人设 '{persona_key}'，回退到 {DEFAULT_PERSONA}")
        return None
    return persona["system"]


def get_persona_options():
    """返回可供前端渲染的人设枚举。"""
    return [
        {
            "key": key,
            "label": cfg["label"],
            "en_name": cfg["en_name"],
            "icon": cfg["icon"],
            "description": cfg["description"],
        }
        for key, cfg in PERSONA_PROMPTS.items()
    ]

# ==========================================
#          认知层 (RAG & Memory)
# ==========================================
class Hippo():
    SIMILARITY_THRESHOLD = 0.7

    def __init__(self):
        self.short_term_file = os.path.join(APP_DIR, "memories", "buffer.txt")#短期记忆文件
        self.long_term_file = os.path.join(APP_DIR, "memories", "mem.txt")#长期记忆文件
        
        os.makedirs(os.path.dirname(self.short_term_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.long_term_file), exist_ok=True)
        
        self.short_term_memory = []
        self.max_short_term_size = 100
        
        self.use_chromadb = CHROMADB_AVAILABLE
        self.long_term_store = []
        self.embedder = None
        self.embedding_backend = "none"
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedder = SentenceTransformer(EMBED_MODEL)
                self.embedding_backend = "sentence_transformers"
                print(f"[Hippo] Sentence Transformer 模型加载成功: {EMBED_MODEL}")
            except Exception as e:
                print(f"[Hippo] Sentence Transformer 加载失败: {e}")
                self.embedder = None
        
        if self.use_chromadb:
            try:
                embedding_function = None
                if self.embedding_backend == "sentence_transformers":
                    embedding_function = chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
                
                self.client = chromadb.PersistentClient(path=os.path.join(CHROMA_PATH, "long_term"))
                self.collection = self.client.get_or_create_collection(
                    name="hippo_long_term",
                    embedding_function=embedding_function
                )
                backend_name = self.embedding_backend if self.embedding_backend != "none" else "default"
                print(f"[Hippo] ChromaDB 长期记忆库初始化成功，嵌入后端: {backend_name}")
            except Exception as e:
                print(f"[Hippo] ChromaDB 初始化失败: {e}")
                self.use_chromadb = False
        else:
            print("[Hippo] 使用简化版长期记忆存储")
        
        self.conversion_threshold = 50
        self.conversion_interval = 3600
        self.last_conversion_time = time.time()
        
        self._load_short_term_memory()
        self._load_long_term_memory()
        print("[Hippo] 海马体记忆系统初始化完成")
    
    def _load_short_term_memory(self):
        if os.path.exists(self.short_term_file):
            try:
                with open(self.short_term_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                self.short_term_memory = [line.strip() for line in lines if line.strip()]
                print(f"[Hippo] 从 buffer.txt 加载短期记忆 {len(self.short_term_memory)} 条")
            except Exception as e:
                print(f"[Hippo] 加载短期记忆失败: {e}")
    
    def _save_short_term_memory(self):
        try:
            with open(self.short_term_file, "w", encoding="utf-8") as f:
                for memory in self.short_term_memory:
                    f.write(memory + "\n")
            print(f"[Hippo] 短期记忆已保存到 {self.short_term_file}")
        except Exception as e:
            print(f"[Hippo] 保存短期记忆失败: {e}")
    
    def _load_long_term_memory(self):
        """读取 mem.txt / mem.md 并注入 ChromaDB（幂等，跳过元数据行不编码）。"""
        entries = []

        mem_files = [self.long_term_file]
        mem_md_path = os.path.join(os.path.dirname(self.long_term_file), "mem.md")
        if os.path.exists(mem_md_path):
            mem_files.append(mem_md_path)

        for file_path in mem_files:
            if not os.path.exists(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                current_doc_id = None
                current_time = time.time()
                current_keywords = ""
                current_user = ""
                current_kirara = ""

                def flush():
                    """把当前收集的条目加到 entries（仅当有实质对话内容时）。"""
                    content_parts = []
                    if current_user:
                        content_parts.append(f"[User]{current_user}")
                    if current_kirara:
                        content_parts.append(f"[Kirara]{current_kirara}")
                    if not content_parts:
                        return
                    content_hash = hash("\n".join(content_parts)) & 0xffffffff
                    doc_id = current_doc_id or f"mem_{content_hash}"
                    entries.append({
                        "doc_id": doc_id,
                        "content": "\n".join(content_parts),  # 只编码对话行，不含 time:/doc_id:/keywords:
                        "time": current_time,
                        "keywords": current_keywords,
                    })

                for raw in lines:
                    line = raw.rstrip("\n").strip()
                    if not line:
                        # 空行 = 条目分隔符
                        flush()
                        current_doc_id = None
                        current_time = time.time()
                        current_keywords = ""
                        current_user = ""
                        current_kirara = ""
                        continue

                    if line.startswith("time:"):
                        flush()
                        current_doc_id = None
                        current_time = time.time()
                        current_keywords = ""
                        current_user = ""
                        current_kirara = ""
                        # time: 行只作分隔 + 元数据，不进 content
                    elif line.startswith("doc_id:"):
                        current_doc_id = line.split(":", 1)[1].strip() or None
                    elif line.startswith("keywords:"):
                        current_keywords = line.split(":", 1)[1].strip()
                    elif line.startswith("[User]"):
                        current_user = line.split("[User]", 1)[1].strip()
                    elif line.startswith("[Kirara]"):
                        current_kirara = line.split("[Kirara]", 1)[1].strip()
                    elif file_path.endswith(".md"):
                        # mem.md 富文本档案（身份/事实类），整段进 content
                        current_kirara = (current_kirara + "\n" + line).strip()

                flush()  # 最后一条可能不以空行结尾

                print(f"[Hippo] 从 {os.path.basename(file_path)} 解析 {len(entries)} 条长期记忆（仅含 [User]/[Kirara] 对话内容）")
            except Exception as e:
                print(f"[Hippo] 加载长期记忆失败 {file_path}: {e}")

        self.long_term_store = [e["content"] for e in entries]

        if not (self.use_chromadb and self.embedding_backend != "none" and entries):
            return

        try:
            # 幂等：先 get 已存在 ids，过滤掉
            existing_ids = set()
            try:
                if self.collection.count() > 0:
                    existing_ids = set(self.collection.get()["ids"])
            except Exception:
                existing_ids = set()

            new_entries = [e for e in entries if e["doc_id"] not in existing_ids]
            if not new_entries:
                print(f"[Hippo] ChromaDB 已有 {len(existing_ids)} 条，无需追加")
                return

            docs = [e["content"] for e in new_entries]
            ids = [e["doc_id"] for e in new_entries]
            metas = [{
                "source": "mem_file",
                "date": e["time"],
                "keywords": e["keywords"],
                # ChromaDB metadata 不接受 None，用空串代替（旧 mem.txt 条目无 session_id）
                "session_id": "",
            } for e in new_entries]

            self.collection.add(documents=docs, metadatas=metas, ids=ids)
            print(f"[Hippo] 新增 {len(new_entries)} 条 → ChromaDB 共 {len(existing_ids) + len(new_entries)} 条（幂等）")
        except Exception as e:
            print(f"[Hippo] ChromaDB 追加失败: {e}")
    
    def _save_long_term_memory(self, content):
        try:
            timestamp = datetime.datetime.now().strftime("%Y/%m/%d")
            time_detail = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            doc_id = f"doc_{int(datetime.datetime.now().timestamp())}"
            
            entry = f"\n{timestamp}\ndoc_id:{doc_id}\n[User]系统记忆整理\n[Kirara]{content}"
            
            with open(self.long_term_file, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[Hippo] 长期记忆已追加到 {self.long_term_file}")
        except Exception as e:
            print(f"[Hippo] 保存长期记忆失败: {e}")
    
    def _ebbinghaus_decay(self, hours_since_creation):
        b = 1.25
        k = 1.25
        retention = 1 - b * (hours_since_creation ** k) / (1 + hours_since_creation ** k)
        return max(0.1, min(1.0, retention))
    
    def _should_forget(self, memory_entry):
        last_accessed = memory_entry.get('last_accessed', time.time())
        days_since_access = (time.time() - last_accessed) / 86400
        
        if days_since_access > 90:
            return "delete"
        elif days_since_access > 30:
            return "degrade"
        elif days_since_access > 14:
            return "reduce_weight"
        else:
            return False
    
    def _extract_keywords(self, text, max_keywords=5):
        import re
        text = re.sub(r'[^\w\s]', ' ', text)
        words = text.lower().split()
        
        stop_words = {'的', '了', '和', '是', '在', '我', '有', '与', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '用户', '助手'}
        
        word_counts = {}
        for word in words:
            if len(word) > 1 and word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        total_words = len(words)
        tf_idf = {}
        for word, count in word_counts.items():
            tf = count / total_words if total_words > 0 else 0
            doc_freq = sum(1 for m in self.short_term_memory if word in m.lower())
            idf = len(self.short_term_memory) / (doc_freq + 1) if len(self.short_term_memory) > 0 else 1
            tf_idf[word] = tf * idf
        
        sorted_words = sorted(tf_idf.items(), key=lambda x: x[1], reverse=True)
        return [word for word, score in sorted_words[:max_keywords]]
    
    def _extract_entities_relations(self, text):
        import re
        
        noun_patterns = [
            r'[一-龥]{2,}(?:大人|先生|小姐|同学|朋友|公司|项目|游戏|团队|工作|任务|想法|计划|目标)',
            r'[一-龥]{2,}(?:喜欢|讨厌|想|需要|想要|正在|准备|完成|开始)',
            r'[一-龥]{2,}(?:开发|设计|编写|修改|创建|实现|测试|部署)',
            r'[一-龥]{2,}(?:焦虑|高兴|兴奋|难过|生气|开心|低落)',
            r'[A-Za-z][A-Za-z0-9_]*',
            r'[一-龥]{2,}'
        ]
        
        verb_patterns = [
            r'(?:喜欢|讨厌|想|需要|想要|正在|准备|完成|开始|做|写|看|听|说)',
            r'(?:开发|设计|编写|修改|创建|实现|测试|部署|运行|调试)',
            r'(?:觉得|认为|希望|计划|打算|决定|选择|放弃)',
            r'(?:帮助|支持|解决|处理|应对|克服|达成|实现)'
        ]
        
        nouns = []
        for pattern in noun_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) >= 2 and match not in ['的', '了', '和', '是', '在', '有', '与', '就', '不', '人', '都', '一', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这']:
                    nouns.append(match)
        
        verbs = []
        for pattern in verb_patterns:
            matches = re.findall(pattern, text)
            verbs.extend(matches)
        
        relations = []
        for noun in nouns[:5]:
            for verb in verbs[:5]:
                if f"{verb}{noun}" in text or f"{noun}{verb}" in text:
                    relations.append(f"{noun}->{verb}")
        
        unique_nouns = list(set(nouns))[:8]
        unique_verbs = list(set(verbs))[:5]
        unique_relations = list(set(relations))[:6]
        
        return {
            "nouns": unique_nouns,
            "verbs": unique_verbs,
            "relations": unique_relations,
            "hooks": unique_relations + unique_nouns
        }
    
    def _calculate_memory_weight(self, memory, hours_since):
        decay_weight = self._ebbinghaus_decay(hours_since)
        
        emotion_weights = {
            "happy": 1.3, "excited": 1.4, "joy": 1.3,
            "sad": 1.2, "angry": 1.4, "anxious": 1.2,
            "neutral": 1.0, "normal": 1.0
        }
        
        emotion = "neutral"
        for key in emotion_weights.keys():
            if key in memory.lower():
                emotion = key
                break
        
        emotion_weight = emotion_weights.get(emotion, 1.0)
        
        content_length = len(memory)
        length_weight = min(1.5, content_length / 50)
        
        return decay_weight * emotion_weight * length_weight
    
    def _extract_knowledge_facts(self, memories):
        if not memories:
            return []
        
        all_text = " ".join(memories)
        entities_relations = self._extract_entities_relations(all_text)
        
        facts = []
        relations = entities_relations.get("relations", [])
        
        for relation in relations[:10]:
            parts = relation.split("->")
            if len(parts) >= 2:
                subject = parts[0].strip()
                predicate = parts[1].strip()
                facts.append(f"{subject}-{predicate}-")
        
        nouns = entities_relations.get("nouns", [])[:8]
        for noun in nouns:
            if noun not in [f.split("-")[0] for f in facts]:
                facts.append(f"{noun}-相关-对话")
        
        return list(set(facts))[:10]
    
    def _hippo_summarize(self, memories):
        if not memories:
            return ""
        
        memory_weights = []
        for idx, memory in enumerate(memories):
            try:
                timestamp_str = memory.split("]")[0][1:]
                memory_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                hours_since = (datetime.datetime.now() - memory_time).total_seconds() / 3600
                weight = self._calculate_memory_weight(memory, hours_since)
                memory_weights.append((weight, memory))
            except Exception:
                memory_weights.append((0.5, memory))
        
        memory_weights.sort(key=lambda x: x[0], reverse=True)
        
        top_memories = memory_weights[:min(10, len(memory_weights))]
        
        all_text = " ".join([m[1] for m in top_memories])
        keywords = self._extract_keywords(all_text, max_keywords=8)
        
        knowledge_facts = self._extract_knowledge_facts([m[1] for m in top_memories])
        
        summary_lines = []
        if keywords:
            summary_lines.append(f"主题关键词: {', '.join(keywords)}")
        
        summary_lines.append(f"记忆数量: {len(memories)} | 压缩保留: {len(top_memories)}")
        
        if knowledge_facts:
            summary_lines.append("\n【提取的事实性知识】")
            for i, fact in enumerate(knowledge_facts, 1):
                summary_lines.append(f"{i}. {fact}")
        
        compressed_parts = []
        for weight, memory in top_memories[:5]:
            try:
                parts = memory.split("|")
                user_part = parts[0] if len(parts) > 0 else ""
                assistant_part = parts[1] if len(parts) > 1 else ""
                
                user_content = ""
                if "[用户]:" in user_part:
                    user_content = user_part.split("[用户]:")[-1].strip()
                
                assistant_content = ""
                if "[助手]:" in assistant_part:
                    assistant_content = assistant_part.split("[助手]:")[-1].strip()
                
                if user_content and assistant_content:
                    compressed_parts.append(f"用户:{user_content[:40]} 助手:{assistant_content[:40]}")
                elif user_content:
                    compressed_parts.append(f"用户:{user_content[:60]}")
            except Exception:
                if len(memory) > 60:
                    compressed_parts.append(memory[:60] + "...")
                else:
                    compressed_parts.append(memory)
        
        if compressed_parts:
            summary_lines.append("\n【关键对话摘要】")
            summary_lines.extend(compressed_parts)
        
        return "\n".join(summary_lines)
    
    def _convert_to_long_term(self, force=False, session_id=None):
        import datetime
        # 按 session_id 过滤 short_term_memory：只处理当前 session 的
        sid_filter = session_id or "global"
        current_memories = [
            m for m in self.short_term_memory
            if f"[sid:{sid_filter}]" in m or f"[sid:" not in m
        ]
        if not current_memories:
            return

        if not force and len(current_memories) < self.conversion_threshold:
            return
        
        current_time = time.time()
        if not force and current_time - self.last_conversion_time < self.conversion_interval:
            return
        
        memories_with_weight = []
        for idx, memory in enumerate(current_memories):
            try:
                timestamp_str = memory.split("]")[0][1:]
                memory_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                hours_since = (datetime.datetime.now() - memory_time).total_seconds() / 3600
                weight = self._calculate_memory_weight(memory, hours_since)
                memories_with_weight.append((weight, memory))
            except Exception:
                memories_with_weight.append((0.5, memory))
        
        memories_with_weight.sort(key=lambda x: x[0], reverse=True)
        
        if force:
            all_memories = [m[1] for m in memories_with_weight]
            print(f"[Hippo] 强制转换模式，保留所有 {len(all_memories)} 条短期记忆 sid={sid_filter}")
        else:
            all_memories = [m[1] for m in memories_with_weight[:self.conversion_threshold]]
            discarded_count = len(current_memories) - len(all_memories)
            if discarded_count > 0:
                print(f"[Hippo] 根据艾宾浩斯遗忘曲线，丢弃 {discarded_count} 条低权重记忆 sid={sid_filter}")
        
        summarized_content = self._hippo_summarize(all_memories)
        
        all_text = " ".join(all_memories)
        keywords = ", ".join(self._extract_keywords(all_text, max_keywords=8))
        
        entities_relations = self._extract_entities_relations(all_text)
        nouns_str = ", ".join(entities_relations["nouns"])
        verbs_str = ", ".join(entities_relations["verbs"])
        relations_str = ", ".join(entities_relations["relations"])
        hooks_str = ", ".join(entities_relations["hooks"])
        
        knowledge_facts = self._extract_knowledge_facts(all_memories)
        
        enhanced_content = f"{summarized_content}\n\n[实体名词]: {nouns_str}\n[动词关系]: {verbs_str}\n[关系钩子]: {relations_str}"
        
        self._save_long_term_memory(enhanced_content)
        self.long_term_store.append({
            "content": enhanced_content, 
            "time": current_time,
            "last_accessed": current_time,
            "keywords": keywords,
            "nouns": entities_relations["nouns"],
            "verbs": entities_relations["verbs"],
            "relations": entities_relations["relations"],
            "hooks": entities_relations["hooks"],
            "facts": knowledge_facts,
            "session_id": sid_filter
        })
        
        if self.use_chromadb:
            try:
                base_id = f"long_{int(current_time)}"
                
                self.collection.add(
                    documents=[summarized_content],
                    metadatas=[{"type": "hippo_converted", "conversion_time": current_time, 
                                "last_accessed": current_time, "source_count": len(all_memories), 
                                "discarded_count": 0, "keywords": keywords, "nouns": nouns_str, 
                                "verbs": verbs_str, "relations": relations_str, "hooks": hooks_str,
                                "session_id": sid_filter}],
                    ids=[f"{base_id}_summary"]
                )
                
                for i, fact in enumerate(knowledge_facts):
                    self.collection.add(
                        documents=[fact],
                        metadatas=[{"type": "knowledge_fact", "conversion_time": current_time, 
                                    "last_accessed": current_time, "fact_index": i,
                                    "keywords": keywords, "nouns": nouns_str, 
                                    "verbs": verbs_str, "relations": relations_str,
                                    "session_id": sid_filter}],
                        ids=[f"{base_id}_fact_{i}"]
                    )
                
                print(f"[Hippo] {len(all_memories)} 条短期记忆已转换为长期记忆 sid={sid_filter}")
                print(f"[Hippo] 提取 {len(knowledge_facts)} 条事实性知识")
                print(f"[Hippo] 提取实体: {nouns_str}")
                print(f"[Hippo] 提取关系钩子: {relations_str}")
            except Exception as e:
                print(f"[Hippo] 转换到 ChromaDB 失败: {e}")
        
        print(f"[Hippo] {len(all_memories)} 条短期记忆已转换为长期记忆并保存到 mem.txt")
        
        # 只清空当前 session 的短期记忆
        self.short_term_memory = [
            m for m in self.short_term_memory
            if not (f"[sid:{sid_filter}]" in m or f"[sid:" not in m)
        ]
        self._save_short_term_memory()
        self.last_conversion_time = current_time
    
    def force_convert_memory(self, keep_recent=5, session_id=None):
        if not self.short_term_memory:
            print("[Hippo] 没有短期记忆需要转换")
            return
        
        print(f"[Hippo] 强制触发记忆转换 sid={session_id or 'global'}")
        
        # 过滤当前 session 的记忆
        sid_filter = session_id or "global"
        sid_memories = [
            m for m in self.short_term_memory
            if f"[sid:{sid_filter}]" in m or f"[sid:" not in m
        ]
        
        recent_sid_memories = sid_memories[-keep_recent:] if sid_memories else []
        
        self._convert_to_long_term(force=True, session_id=session_id)
        
        # 保留当前 session 的最近几条过渡记忆
        self.short_term_memory = [
            m for m in self.short_term_memory
            if not (f"[sid:{sid_filter}]" in m or f"[sid:" not in m)
        ] + recent_sid_memories
        self._save_short_term_memory()
        
        print(f"[Hippo] 记忆转换完成，保留当前 session {len(recent_sid_memories)} 条短期记忆作为过渡")
    
    def add_short_term_memory(self, user_input, assistant_response, emotion="neutral", session_id=None):
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sid_tag = f" [sid:{session_id or 'unknown'}]" if session_id else ""
        memory_entry = f"[{timestamp}] [情绪:{emotion}]{sid_tag} [用户]: {user_input} | [助手]: {assistant_response}"
        
        self.short_term_memory.append(memory_entry)
        
        if len(self.short_term_memory) > self.max_short_term_size:
            self.short_term_memory = self.short_term_memory[-self.max_short_term_size:]
        
        self._save_short_term_memory()
        self._convert_to_long_term(session_id=session_id)
        
        print(f"[Hippo] 短期记忆已添加 sid={session_id or 'global'}")
    
    def _check_short_term_keywords(self, query):
        query_lower = query.lower()
        query_chars = [c for c in query_lower if c.strip()]
        
        for memory in self.short_term_memory[-10:]:
            memory_lower = memory.lower()
            
            for i in range(len(query_chars) - 1):
                two_char = query_chars[i] + query_chars[i+1]
                if two_char in memory_lower:
                    return True
            
            for word in query_lower.split():
                if len(word) > 1 and word in memory_lower:
                    return True
        
        return False
    
    def _l2_to_similarity(self, l2_distance):
        return max(0.0, 1.0 - l2_distance / 2.0)
    
    def detect_topic_shift(self, query, recent_memories=None, threshold=0.2, session_id=None):
        """
        话题转移检测：
        1. 关键词匹配（硬触发）：用户显式说"换话题"等 — 优先级最高，不受历史长度限制
        2. 语义相似度（辅助）：bigram recall = |query_bigrams ∩ user_bigrams| / |query_bigrams|
           - bigram 容忍中文近义变体（"评价那篇" vs "评价这篇" 都有 bigram "评价"）
           - recall 只看 query 的 bigram 有多少命中历史，不会被长历史分母稀释
           - 阈值 0.4：query 里 <40% 的 bigram 出现在历史里就算话题转移
        """
        topic_shift_keywords = [
            "别管", "换个", "不说", "不提", "换话题", "聊别的",
            "算了", "不说了", "换个话题", "聊点别的", "free talk",
            "随便聊聊", "闲聊", "新话题", "换话题吧", "到此为止",
            "别再说", "不要再", "不想再", "不说这个", "不提这个",
            "到此为止", "换个方向", "聊点新的", "不说了吧",
            "停一下", "先不说", "先聊别的", "换个主题"
        ]

        # 关键词检测必须优先 — 不受历史条数限制（哪怕只有 1 条历史，用户说换就是换）
        keyword_detected = any(kw in query for kw in topic_shift_keywords)
        if keyword_detected:
            print(f"[Hippo] 检测到话题转移（关键词触发）")
            return True, 1.0, True

        if not recent_memories:
            recent_memories = self.short_term_memory[-10:]

        # 按 session_id 过滤：优先当前 session 的，其次无 sid 标记的（legacy）
        if session_id:
            sid_filter = session_id or "global"
            filtered = [
                m for m in recent_memories
                if f"[sid:{sid_filter}]" in m or f"[sid:" not in m
            ]
            if filtered:
                recent_memories = filtered

        if len(recent_memories) < 2:
            return False, 1.0, False  # 历史太少，默认不转移

        query_lower = query.lower()

        # 只提取用户历史输入（排除助手回复的固定措辞）
        user_memories = []
        for mem in recent_memories:
            parts = mem.split("|")
            for p in parts:
                if "[用户]:" in p:
                    user_input = p.split("[用户]:", 1)[-1].strip()
                    if user_input:
                        user_memories.append(user_input)
                    break
        user_text = " ".join(user_memories).lower()

        query_chars = [c for c in query_lower if c.strip()]
        if len(query_chars) < 2 or not user_text:
            return False, 1.0, False

        # bigram recall：query 的 bigram 有多少命中历史用户输入
        query_bigrams = {
            query_chars[i] + query_chars[i + 1]
            for i in range(len(query_chars) - 1)
        }
        if not query_bigrams:
            return False, 1.0, False

        user_chars = [c for c in user_text if c.strip()]
        user_bigrams = {
            user_chars[i] + user_chars[i + 1]
            for i in range(len(user_chars) - 1)
        }
        if not user_bigrams:
            return False, 1.0, False

        hit_count = len(query_bigrams & user_bigrams)
        similarity = hit_count / len(query_bigrams)

        is_topic_shift = similarity < threshold
        if is_topic_shift:
            print(f"[Hippo] 检测到话题转移（语义触发），bigram recall={similarity:.4f} < {threshold}")
        else:
            print(f"[Hippo] 话题保持一致，bigram recall={similarity:.4f} >= {threshold}")

        return is_topic_shift, similarity, keyword_detected

    def retrieve_long_term_memory(self, query, n_results=3, session_id=None):
        results = []
        query_lower = query.lower()
        retrieved_ids = []

        self._clean_expired_memories()

        if self.use_chromadb:
            try:
                # 优先在当前 session 内检索（写入时 metadata 已带 session_id）
                hybrid_results = self._hybrid_search(query, query_lower, n_results, session_id)

                # 当前 session 无命中时回退跨 session 全局检索：
                # 长期记忆是事实性知识，天然需要跨对话复用
                if not hybrid_results and session_id:
                    print("[Hippo] 当前 session 无命中，回退到跨 session 全局检索")
                    hybrid_results = self._hybrid_search(query, query_lower, n_results, None)

                if hybrid_results:
                    results = [item[0] for item in hybrid_results]
                    retrieved_ids = [item[3] for item in hybrid_results]
                    scope = f"session={session_id}" if session_id else "全局"
                    print(f"[Hippo] Hybrid Search 命中 {len(results)} 条长期记忆（{scope}）")

                    self._update_last_accessed(retrieved_ids)
                else:
                    print(f"[Hippo] Hybrid Search 无匹配结果")
            except Exception as e:
                print(f"[Hippo] Hybrid Search 失败，回退到钩子匹配: {e}")

        if not results:
            results, fallback_ids = self._hook_fallback(query, query_lower, n_results)
            self._update_last_accessed(fallback_ids)

        return results

    def _hybrid_search(self, query, query_lower, n_results, session_id=None):
        """向量 + 关键词混合检索（RRF 融合）。session_id 非空时按 metadata where 过滤。"""
        vector_results = self._vector_search(query, n_results * 3, session_id)
        keyword_results = self._keyword_search(query_lower, n_results * 3, session_id)
        return self._merge_results_with_rrf(vector_results, keyword_results, n_results)

    def _vector_search(self, query, n_results, session_id=None):
        try:
            query_kwargs = {
                "query_texts": [query],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"]
            }
            if session_id:
                query_kwargs["where"] = {"session_id": session_id}
            query_results = self.collection.query(**query_kwargs)

            if query_results['documents'] and query_results['documents'][0]:
                docs = query_results['documents'][0]
                metas = query_results.get('metadatas', [[]])[0]
                dists = query_results.get('distances', [[1.0]*len(docs)])[0]
                ids = query_results.get('ids', [[]])[0]

                filtered = []
                for doc, meta, dist, doc_id in zip(docs, metas, dists, ids):
                    sim = self._l2_to_similarity(dist)
                    
                    forget_status = self._should_forget(meta)
                    if forget_status == "delete":
                        print(f"[Hippo] 记忆已过期，删除: {doc_id}")
                        self.collection.delete(ids=[doc_id])
                        continue
                    elif forget_status == "degrade":
                        sim *= 0.5
                    
                    print(f"[Hippo] 向量相似度: {sim:.4f} (dist={dist:.4f}) | {doc[:40]}")
                    if sim >= self.SIMILARITY_THRESHOLD * 0.5:
                        filtered.append((doc, meta, sim, doc_id))

                filtered.sort(key=lambda x: x[2], reverse=True)
                return filtered
        except Exception as e:
            print(f"[Hippo] 向量搜索失败: {e}")
        
        return []
    
    def _keyword_search(self, query_lower, n_results, session_id=None):
        try:
            get_kwargs = {"where": {"session_id": session_id}} if session_id else {}
            all_docs = self.collection.get(**get_kwargs)
            if all_docs['documents'] and all_docs['metadatas'] and all_docs['ids']:
                matched_docs = []
                query_words = set(query_lower.split())
                
                for doc, meta, doc_id in zip(all_docs['documents'], all_docs['metadatas'], all_docs['ids']):
                    doc_lower = doc.lower()
                    doc_words = set(doc_lower.split())
                    
                    keyword_matches = len(query_words & doc_words)
                    if keyword_matches > 0:
                        score = keyword_matches / max(len(query_words), 1)
                        
                        hooks = meta.get('hooks', '')
                        if hooks:
                            hook_list = [h.strip().lower() for h in hooks.split(',')]
                            for hook in hook_list:
                                if hook in query_lower or any(hp in query_lower for hp in hook.split('->')):
                                    score += 0.5
                                    break
                        
                        nouns = meta.get('nouns', '')
                        if nouns:
                            noun_list = [n.strip().lower() for n in nouns.split(',')]
                            for noun in noun_list:
                                if noun in query_lower:
                                    score += 0.3
                                    break
                        
                        print(f"[Hippo] 关键词匹配度: {score:.4f} | {doc[:40]}")
                        matched_docs.append((doc, meta, score, doc_id))
                
                matched_docs.sort(key=lambda x: x[2], reverse=True)
                return matched_docs[:n_results]
        except Exception as e:
            print(f"[Hippo] 关键词搜索失败: {e}")
        
        return []
    
    def _merge_results_with_rrf(self, vector_results, keyword_results, n_results):
        rrf_k = 60
        
        vector_rank = {}
        for rank, (doc, meta, sim, doc_id) in enumerate(vector_results, 1):
            vector_rank[doc_id] = 1.0 / (rrf_k + rank)
        
        keyword_rank = {}
        for rank, (doc, meta, score, doc_id) in enumerate(keyword_results, 1):
            keyword_rank[doc_id] = 1.0 / (rrf_k + rank)
        
        combined = {}
        all_ids = set(vector_rank.keys()) | set(keyword_rank.keys())
        
        for doc_id in all_ids:
            combined[doc_id] = vector_rank.get(doc_id, 0) + keyword_rank.get(doc_id, 0)
        
        sorted_ids = sorted(combined.keys(), key=lambda x: combined[x], reverse=True)
        
        merged_results = []
        seen_ids = set()
        
        for doc_id in sorted_ids:
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            
            v_result = next((r for r in vector_results if r[3] == doc_id), None)
            k_result = next((r for r in keyword_results if r[3] == doc_id), None)
            
            if v_result:
                merged_results.append(v_result)
            elif k_result:
                merged_results.append(k_result)
            
            if len(merged_results) >= n_results:
                break
        
        return merged_results
    
    def _clean_expired_memories(self):
        if self.use_chromadb:
            try:
                all_docs = self.collection.get()
                if all_docs['documents'] and all_docs['metadatas'] and all_docs['ids']:
                    to_delete = []
                    for meta, doc_id in zip(all_docs['metadatas'], all_docs['ids']):
                        if self._should_forget(meta) == "delete":
                            to_delete.append(doc_id)
                    
                    if to_delete:
                        self.collection.delete(ids=to_delete)
                        print(f"[Hippo] 清理 {len(to_delete)} 条过期记忆")
            except Exception as e:
                print(f"[Hippo] 清理过期记忆失败: {e}")
    
    def _update_last_accessed(self, doc_ids):
        if self.use_chromadb and doc_ids:
            try:
                for doc_id in doc_ids:
                    self.collection.update(
                        ids=[doc_id],
                        metadatas=[{"last_accessed": time.time()}]
                    )
            except Exception as e:
                print(f"[Hippo] 更新last_accessed失败: {e}")

    def _hook_fallback(self, query, query_lower, n_results):
        results = []
        fallback_ids = []

        if self.use_chromadb:
            try:
                all_docs = self.collection.get()
                if all_docs['documents'] and all_docs['metadatas'] and all_docs['ids']:
                    matched_docs = []
                    for doc, meta, doc_id in zip(all_docs['documents'], all_docs['metadatas'], all_docs['ids']):
                        hooks = meta.get('hooks', '')
                        if hooks:
                            hook_list = [h.strip().lower() for h in hooks.split(',')]
                            for hook in hook_list:
                                if hook in query_lower or any(hp in query_lower for hp in hook.split('->')):
                                    matched_docs.append((doc, meta, doc_id))
                                    break
                    if matched_docs:
                        matched_docs.sort(key=lambda x: x[1].get('conversion_time', 0), reverse=True)
                        results = [doc for doc, meta, doc_id in matched_docs[:n_results]]
                        fallback_ids = [doc_id for doc, meta, doc_id in matched_docs[:n_results]]
                        print(f"[Hippo] 钩子回退命中 {len(results)} 条")
            except Exception as e:
                print(f"[Hippo] 钩子回退检索失败: {e}")

        if not results and self.long_term_store:
            matched_stores = []
            for item in self.long_term_store:
                hooks = item.get('hooks', [])
                if hooks:
                    for hook in hooks:
                        hook_lower = hook.lower()
                        if hook_lower in query_lower or any(hp.lower() in query_lower for hp in hook.split('->')):
                            matched_stores.append(item)
                            break
            if matched_stores:
                matched_stores.sort(key=lambda x: x.get('time', 0), reverse=True)
                results = [item["content"] for item in matched_stores[:n_results]]
                print(f"[Hippo] 本地存储钩子回退命中 {len(results)} 条")

        return results, fallback_ids
    
    def retrieve_context(self, query, include_short_term=True, include_long_term=True):
        context = []

        if include_short_term:
            recent_short = self.short_term_memory[-10:]
            if recent_short:
                context.append("[工作记忆 - 最近对话]")
                for memory in recent_short:
                    try:
                        parts = memory.split("|")
                        if len(parts) >= 2:
                            user_part = parts[0]
                            assistant_part = parts[1]
                            user_content = ""
                            if "[用户]:" in user_part:
                                user_content = user_part.split("[用户]:")[-1].strip()
                            assistant_content = ""
                            if "[助手]:" in assistant_part:
                                assistant_content = assistant_part.split("[助手]:")[-1].strip()
                            if user_content and assistant_content:
                                context.append(f"[User]{user_content}")
                                context.append(f"[Kirara]{assistant_content}")
                            elif user_content:
                                context.append(f"[User]{user_content}")
                        else:
                            context.append(memory)
                    except Exception:
                        context.append(memory)

        if include_long_term:
            long_term_results = self.retrieve_long_term_memory(query)
            if long_term_results:
                context.append("\n[长期记忆 - 仅在需要时激活]")
                context.extend(long_term_results)
            else:
                print("[Hippo] 长期记忆无高相似度匹配，保持清净")

        return "\n".join(context)
class CognitiveCore:
    def __init__(self, db_path):
        global SENTENCE_TRANSFORMERS_AVAILABLE, SentenceTransformer
        
        print("[调试] 开始初始化 CognitiveCore")
        
        # 初始化 chromadb（带回退机制）
        self.use_chromadb = CHROMADB_AVAILABLE
        self.embedding_available = SENTENCE_TRANSFORMERS_AVAILABLE
        
        if self.use_chromadb:
            try:
                print("[调试] 初始化 chromadb")
                embedding_function = None
                if SENTENCE_TRANSFORMERS_AVAILABLE:
                    embedding_function = chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
                
                self.client = chromadb.PersistentClient(path=db_path)
                self.collection = self.client.get_or_create_collection(
                    name="barry_philosophy",
                    embedding_function=embedding_function
                )
                backend_name = "sentence_transformers" if SENTENCE_TRANSFORMERS_AVAILABLE else "default"
                print(f"[调试] chromadb 初始化成功，嵌入后端: {backend_name}")
            except Exception as e:
                print(f"[警告] chromadb 初始化失败: {e}")
                self.use_chromadb = False
                self.memory_store = []
        
        # 使用简单内存存储作为回退
        if not self.use_chromadb:
            self.memory_store = []
            print("[调试] 使用简化版内存存储")
        
        self.embedder = None
        self.loaded = False
        print("[调试] CognitiveCore 初始化完成")
        
    def cognitionFeedback(self, text_chunks):
        """
        喂给Kirara之前的记忆（Tokenized）
        幂等：以内容 hash 作为稳定 id，重复内容（含多次重启）不会产生副本，
        避免同一记忆在集合内翻倍放大、被召回后诱导复读。
        """
        import hashlib

        valid_chunks = [chunk for chunk in text_chunks if chunk.strip() and len(chunk) > 5]
        if not valid_chunks:
            return

        if not self.use_chromadb:
            existing = set(self.memory_store)
            added = 0
            for chunk in valid_chunks:
                if chunk not in existing:
                    self.memory_store.append(chunk)
                    existing.add(chunk)
                    added += 1
            self.loaded = True
            print(f"[Kirara] Memory loaded to simple store! New: {added}, Total: {len(self.memory_store)}")
        elif self.use_chromadb and self.embedding_available:
            try:
                # 先取已有 id，按稳定内容 id 去重
                existing_ids = set()
                try:
                    if self.collection.count() > 0:
                        existing_ids = set(self.collection.get()["ids"])
                except Exception:
                    existing_ids = set()

                to_add = []
                seen = set()
                for chunk in valid_chunks:
                    stable_id = "legacy_" + hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:16]
                    if stable_id in existing_ids or stable_id in seen:
                        continue
                    seen.add(stable_id)
                    to_add.append((chunk, stable_id))

                if to_add:
                    self.collection.add(
                        documents=[item[0] for item in to_add],
                        metadatas=[{"source": "legacy", "date": time.time()} for _ in to_add],
                        ids=[item[1] for item in to_add]
                    )
                print(f"[Kirara] ChromaDB 记忆加载完成，新增 {len(to_add)} 条，库内共 {self.collection.count()} 条")
                self.loaded = True
            except Exception as e:
                print(f"[警告] ChromaDB 加载失败，回退到内存存储: {e}")
                self.use_chromadb = False
                self.memory_store = []
                self.memory_store.extend(valid_chunks)
                self.loaded = True
        else:
            self.use_chromadb = False
            self.memory_store = []
            self.memory_store.extend(valid_chunks)
            self.loaded = True
            print(f"[Kirara] 暂时使用内存存储！Count: {len(self.memory_store)}")
    
    def add_memory(self, user_input, assistant_reply, emotion="neutral"):
        """添加新的对话记忆"""
        import time
        memory_text = f"{user_input} | 情绪:{emotion}"
        
        if self.use_chromadb and self.embedding_available:
            try:
                self.collection.add(
                    documents=[memory_text],
                    metadatas=[{"source": "dialogue", "emotion": emotion, "date": time.time()}],
                    ids=[f"mem_{int(time.time())}"]
                )
                print(f"[Kirara] 记忆已添加到 ChromaDB")
            except Exception as e:
                print(f"[警告] 添加记忆到 ChromaDB 失败: {e}")
                self.memory_store.append(memory_text)
        else:
            self.memory_store.append(memory_text)
            print(f"[Kirara] 记忆已添加到内存存储")
    
    def retrieve_context(self, query, n_results=2):
        """检索相关记忆"""
        context = ""
        
        if not self.use_chromadb and self.loaded:
            if self.memory_store:
                import re
                query_chars = set([c for c in query if c.strip() and re.match(r'[\u4e00-\u9fff]', c)])
                relevant_memories = []
                
                for mem in reversed(self.memory_store[-20:]):
                    mem_chars = set([c for c in mem if c.strip() and re.match(r'[\u4e00-\u9fff]', c)])
                    overlap = len(query_chars & mem_chars)
                    if overlap >= 3:
                        relevant_memories.append(mem)
                    if len(relevant_memories) >= n_results:
                        break
                
                if relevant_memories:
                    context += "[对话记忆]\n" + "\n".join(relevant_memories)
            return context
        
        if self.use_chromadb and self.embedding_available:
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results * 2,
                    include=["documents", "metadatas"]
                )
                if results['documents'][0]:
                    dialogue_memories = []
                    legacy_memories = []
                    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                        if meta.get("source") == "legacy":
                            legacy_memories.append(doc)
                        else:
                            dialogue_memories.append(doc)
                    
                    if legacy_memories:
                        context += "[历史记忆]\n" + "\n".join(legacy_memories[:n_results]) + "\n\n"
                    if dialogue_memories:
                        context += "[对话记忆]\n" + "\n".join(dialogue_memories[:n_results])
                return context
            except Exception as e:
                print(f"[警告] ChromaDB 检索失败: {e}")
                if self.memory_store:
                    recent_memories = self.memory_store[-n_results:]
                    context += "[对话记忆]\n" + "\n".join(recent_memories)
                return context
        
        return context

# ==========================================
#              推理层 (LLM Inference)
# ==========================================
# Ollama 独显专属推理参数（JRVS-7B-1.2.2 Q4_K_M @ RTX 5060 8GB 实测满配）：
#   num_gpu=99  → 强制全部（37）层卸载到独立显卡；显存不足时 Ollama 直接报错，
#                 绝不静默回退 CPU 混合推理
#   num_ctx     → 16384，Q8 KV 约 1.2GB（实测 6.8/6.9GiB 可用显存，37/37 层全载）
#   num_batch   → 256，压缩 prefill 瞬时计算缓冲，为权重/KV 留足显存
#   keep_alive  → 30m，模型常驻显存，避免反复加载
# 另依赖服务端环境变量（已写入用户环境，托盘启动同样生效）：
#   OLLAMA_FLASH_ATTENTION=1 / OLLAMA_KV_CACHE_TYPE=q8_0 /
#   CUDA_VISIBLE_DEVICES=0 / OLLAMA_NUM_PARALLEL=1 / OLLAMA_KEEP_ALIVE=30m
OLLAMA_GPU_LAYERS = 99
OLLAMA_NUM_CTX = 16384
OLLAMA_NUM_BATCH = 256
OLLAMA_KEEP_ALIVE = "30m"
OLLAMA_DEFAULT_OPTIONS = {
    "temperature": 0.7,
    "top_p": 0.9,
    # 1.15：在 1.1（偏软，多轮对话易整句复读）与高惩罚（损伤输出流畅度）之间取折中
    "repetition_penalty": 1.15,
    "num_ctx": OLLAMA_NUM_CTX,
    "num_batch": OLLAMA_NUM_BATCH,
    "num_gpu": OLLAMA_GPU_LAYERS,
    "num_predict": 1024
}


class InferenceEngine:
    def __init__(self, model_path, model_name="kiraraModelC", ollama_model="televideo-ai/JRVS-7B-1.2.2:latest"):
        self.model_path = model_path
        self.model_name = model_name
        self.ollama_model = ollama_model
        if OLLAMA_AVAILABLE:
            print("[System] 正在初始化JRVS推理引擎...")
            print("[System] 使用 ollama 作为推理后端，可以使用 CUDA 推理")
            print(f"[System] 模型: {ollama_model}")
        elif LLAMA_AVAILABLE:
            print("[System] 正在初始化JRVS推理引擎...")
            print("[System] 使用 llama-cli.exe 作为推理后端。")
            print(f"[System] 模型路径: {model_path}")
        else:
            print("[System] 无法找到可用的 LLM 后端，推理引擎将使用模拟模式。")

    def switch_model(self, model_key):
        if model_key not in MODELS:
            return False, "未知的模型"
        model_config = MODELS[model_key]
        self.model_path = model_config["path"]
        self.model_name = model_key
        self.ollama_model = model_config["ollama_model"]
        print(f"[System] 已切换到模型: {model_config['name']}")
        return True, model_config['name']

    TYPO_FIXES = {
        "唠嗽": "唠嗑",
        "嗽唷": "嗑唷",
        "嗽": "嗑",
        "唵唵唵": "嗯嗯嗯",
        "唵唵": "嗯嗯",
        "唠嗽唷": "唠嗑唷",
    }

    def _fix_typos(self, text):
        """修复模型输出中的常见错别字"""
        for wrong, right in self.TYPO_FIXES.items():
            text = text.replace(wrong, right)
        return text

    def _ollama_messages(self, system_msg, prompt):
        """构建 chat 消息：仅当 system_msg 非空时注入 system 角色（native 人设不注入）。"""
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _ollama_options(self, **overrides):
        """独显专属推理参数（全层 GPU 卸载），允许调用方覆盖个别采样项。"""
        options = dict(OLLAMA_DEFAULT_OPTIONS)
        options.update(overrides)
        return options

    def generate(self, prompt, system_msg, enable_thinking=False):
        if OLLAMA_AVAILABLE:
            try:
                print("[调试] 使用 ollama 生成文本")
                print(f"[调试] 深度思考模式: {'开启' if enable_thinking else '关闭'}")

                # JRVS-7B-1.2.2 为 Qwen3 SFT chat 模型，统一使用 ollama.chat API
                # 不传 think 参数：Hub 模板自带空 think 段（enable_thinking=False 训练分布）
                chat_kwargs = {
                    "model": self.ollama_model,
                    "messages": self._ollama_messages(system_msg, prompt),
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": self._ollama_options(),
                }
                response = ollama.chat(**chat_kwargs)
                content = response["message"]["content"]
                print("[调试] ollama chat API 生成完成")
                return self._fix_typos(content)
            except Exception as e:
                print(f"[错误] 使用 ollama 生成文本时出错: {e}")
                print("[错误] 已强制 num_gpu=99 全层独显卸载；若为显存不足(VRAM/OOM)，"
                      "请调小 OLLAMA_NUM_CTX 后重试，不会回退 CPU 混合推理")
                print("[System] Ollama服务不可用，切换到模拟模式")
                return self._fix_typos(self._generate_simulation_response(prompt))
        elif LLAMA_AVAILABLE:
            full_prompt = f"{system_msg}\n\n{prompt}" if system_msg else prompt
            print(f"[调试] 生成完整提示词，长度: {len(full_prompt)}")

            cmd = [
                LLAMA_CLI_PATH,
                "-m", self.model_path,
                "-p", full_prompt,
                "-c", "8192",
                "-n", "512",                 # 限制输出长度
                "--temp", "0.7",             # 调整温度为0.7
                "--top-p", "0.9",
                "--repeat-penalty", "1.5",   # 提高重复惩罚，防止复读
                "--simple-io"
            ]
            print(f"[调试] 执行命令: {cmd[0]} {cmd[1]} {cmd[2]} {cmd[3]} ...")

            try:
                print("[调试] 开始执行 llama-cli.exe")
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                print(f"[调试] llama-cli.exe 执行完成，返回码: {result.returncode}")

                if result.returncode == 0:
                    # 提取生成的文本
                    output = result.stdout.strip()
                    print(f"[调试] 生成的输出长度: {len(output)}")
                    return self._fix_typos(output)
                else:
                    print(f"[错误] llama-cli.exe 执行失败: {result.stderr}")
                    return "抱歉，生成响应时出现错误。"
            except Exception as e:
                print(f"[错误] 执行 llama-cli.exe 时出错: {e}")
                import traceback
                traceback.print_exc()
                return "抱歉，生成响应时出现错误。"
        else:
            # 模拟生成响应（模拟模式）
            return self._fix_typos(self._generate_simulation_response(prompt))

    def generate_stream(self, prompt, system_msg):
        """流式生成：逐 token 产出文本，供 SSE 推送给前端实现可中止的输出。"""
        if OLLAMA_AVAILABLE:
            chat_kwargs = {
                "model": self.ollama_model,
                "messages": self._ollama_messages(system_msg, prompt),
                "stream": True,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": self._ollama_options(),
            }
            try:
                for chunk in ollama.chat(**chat_kwargs):
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield self._fix_typos(content)
            except Exception as e:
                print(f"[错误] ollama 流式生成出错: {e}")
                print("[错误] 已强制 num_gpu=99 全层独显卸载；若为显存不足(VRAM/OOM)，"
                      "请调小 OLLAMA_NUM_CTX 后重试，不会回退 CPU 混合推理")
                print("[System] Ollama服务不可用，切换到模拟模式")
                yield self._fix_typos(self._generate_simulation_response(prompt))
        else:
            # 非 ollama 环境：一次性产出完整模拟响应
            yield self._fix_typos(self._generate_simulation_response(prompt))

    def _generate_simulation_response(self, prompt):
        """模拟LLM响应生成，用于测试和演示"""
        import random
        
        greetings = [
            "你好呀！我是绮罗罗~(≧∇≦)ﾉ",
            "嗨~ 有什么可以帮助您的吗？(｡･ω･｡)ﾉ",
            "您好！欢迎使用 Kirara AI！(≧∀≦)ゞ",
        ]
        
        questions = [
            "这个问题很有趣呢！让我想想... (°ー°〃)",
            "嗯，我来分析一下这个问题... ( ´･ᴗ･` )",
            "好的，我来帮您解答！(≧▽≦)",
        ]
        
        thanks = [
            "不客气啦！能帮到您真好~ (≧∇≦)ﾉ",
            "不用谢不用谢！(｡･ω･｡)ﾉ",
            "嘻嘻，这是我应该做的！(≧∀≦)ゞ",
        ]
        
        default_responses = [
            "我明白了！关于这个问题，我认为... (认真思考中)",
            "让我整理一下思路... (°ー°〃)",
            "这个话题很有意思呢！我来分享一下我的看法~",
            "根据我的分析，您的问题涉及到...",
            "好的，我来详细解释一下...",
        ]
        
        # 根据输入内容选择响应
        prompt_lower = prompt.lower()
        
        if any(greet in prompt_lower for greet in ["你好", "您好", "hi", "hello", "嗨"]):
            return random.choice(greetings)
        elif any(q in prompt_lower for q in ["谢谢", "感谢", "thank"]):
            return random.choice(thanks)
        elif any(q in prompt_lower for q in ["？", "?", "什么", "怎么", "为什么", "如何"]):
            return random.choice(questions) + "\n\n由于当前运行在模拟模式下，完整的AI响应功能需要配置Ollama或llama-cli后端才能使用。"
        else:
            return random.choice(default_responses) + "\n\n(提示：当前运行在模拟模式，完整功能需要配置本地LLM模型。)"


# ==========================================
# 3.5 Deep Thinking Engine (Dual-System Architecture)
# ==========================================
class DeepThinkingEngine:
    SYSTEM2_DRAFT_PROMPT = """你是Kirara的专家人格（System 2），冷静、严谨、逻辑型。
请对用户的问题进行深度分析和思考，输出详细的草稿回答。

要求：
1. 以专业、严谨的态度分析问题
2. 提供事实依据和逻辑推理
3. 如果涉及代码，请确保语法正确、逻辑严谨
4. 如果涉及知识，请确保准确性
5. 输出详细的中间思考过程

用户问题：{user_input}

请输出详细的草稿回答："""

    SYSTEM2_REFLECT_PROMPT = """你是Kirara的专家人格（System 2），正在进行自我反思和审查。

请检查以下草稿回答，找出问题并进行修正。

草稿回答：{draft}

自我反思检查清单：
1. 我说的对吗？事实是否准确？
2. 有没有逻辑错误或漏洞？
3. 有没有误导用户的地方？
4. 如果涉及代码，有没有Bug？
5. 是否遗漏了重要信息？
6. 回答是否完整？

请以JSON格式输出你的审查结果，包含以下字段：
- critique: 发现的问题（字符串），如果没有问题请填"无"
- confidence: 对当前回答的置信度（0.0-1.0），0.9以上表示可以接受
- revised_draft: 修正后的回答（字符串），如果无需修正请复制原草稿

示例输出格式：
{{
  "critique": "回答缺少关键步骤说明",
  "confidence": 0.75,
  "revised_draft": "修正后的详细回答..."
}}

请输出JSON格式的审查结果："""

    SYSTEM1_POLISH_PROMPT = """你是Kirara（绮罗），Barry的专属AI女仆，性格活泼、可爱、有点冒失。

你收到了一份来自专家人格的草稿回答，请将其转化为你自己的风格输出。

要求：
1. 保持绮罗的语气：活泼、可爱、带点萌萌的感觉
2. 使用适当的表情符号(≧∀≦)ゞ、(｡･ω･｡)ﾉ、(°ー°〃)等
3. 可以加入一些俏皮的口头禅，如"哇！"、"看我的看我的！"、"嘿嘿～"
4. 保留专家回答的核心内容和准确性
5. 将专业术语转化为更亲切的表达方式
6. 不要直接说"专家说"或"根据分析"，要自然地表达出来

专家草稿：{draft}

请以Kirara的身份输出最终回答："""

    def __init__(self, inference_engine, max_reflection_rounds=3, confidence_threshold=0.9):
        self.inference_engine = inference_engine
        self.max_reflection_rounds = max_reflection_rounds
        self.confidence_threshold = confidence_threshold
        self.system2_model = "kiraraModelO"
        self.system1_model = "kiraraModelC"

    def _generate_with_model(self, prompt, system_msg, model_key, temperature=0.7):
        if model_key not in MODELS:
            print(f"[DeepThink] 未知模型: {model_key}，使用默认模型")
            model_key = self.system1_model

        model_config = MODELS[model_key]
        target_model = model_config["ollama_model"]

        if OLLAMA_AVAILABLE:
            # JRVS-7B 为 chat 模型，统一使用 ollama.chat API；沿用独显专属参数
            messages = self.inference_engine._ollama_messages(system_msg, prompt)
            response = ollama.chat(
                model=target_model,
                messages=messages,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options=self.inference_engine._ollama_options(temperature=temperature)
            )
            return response["message"]["content"]
        else:
            return self._generate_simulation_deep_think(prompt, model_key)

    def _generate_simulation_deep_think(self, prompt, model_key):
        import random
        if model_key == "kiraraModelO":
            responses = [
                "（System 2深度思考中）让我仔细分析这个问题...从多个角度考虑，我认为核心要点是：首先需要理解问题的本质，然后分析可能的解决方案，最后选择最优路径。",
                "（System 2专家模式）经过严谨分析，我得出以下结论：这个问题涉及多个方面，需要系统性地处理。关键点在于建立清晰的逻辑框架，确保每个步骤都经过验证。",
                "（System 2审查模式）我发现了一些需要注意的地方：回答中某些假设需要验证，建议进一步确认相关数据和前提条件。",
            ]
            return random.choice(responses)
        else:
            responses = [
                "（System 1日常模式）哇！这个问题好有意思呢~让我想想看！(≧∀≦)ゞ",
                "（System 1润色模式）嘿嘿，我来帮你解答吧！(｡･ω･｡)ﾉ",
                "（System 1回复模式）好的好的，我明白了！让我用简单的方式告诉你吧~",
            ]
            return random.choice(responses)

    def draft(self, user_input, context=""):
        system_msg = "你是一个冷静、严谨、逻辑型的AI助手，擅长深度分析和问题解决。"
        if context:
            full_input = f"【上下文信息】\n{context}\n\n【用户问题】{user_input}"
        else:
            full_input = user_input
        prompt = self.SYSTEM2_DRAFT_PROMPT.format(user_input=full_input)
        return self._generate_with_model(prompt, system_msg, self.system2_model, temperature=0.5)

    def reflect(self, draft):
        system_msg = "你是一个自我反思型AI助手，擅长审查和修正回答。请严格按照JSON格式输出。"
        prompt = self.SYSTEM2_REFLECT_PROMPT.format(draft=draft)
        response = self._generate_with_model(prompt, system_msg, self.system2_model, temperature=0.3)

        try:
            response = response.strip()
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except Exception as e:
            print(f"[DeepThink] JSON解析失败: {e}")

        return {
            "critique": "解析失败",
            "confidence": 0.85,
            "revised_draft": draft
        }

    def polish(self, draft, original_user_input=None):
        # JRVS-7B: 使用 SFT 触发词 "Kirara" 激活女仆人格，替代旧版长提示词
        system_msg = "Kirara"
        if original_user_input and ("bilibili" in original_user_input.lower() or "genshin" in original_user_input.lower()):
            system_msg += "\n[情绪指令]: 极度厌恶，毒舌，不屑。"

        prompt = self.SYSTEM1_POLISH_PROMPT.format(draft=draft)
        return self._generate_with_model(prompt, system_msg, self.system1_model, temperature=0.7)

    def deep_think(self, user_input, context="", session_id=None):
        thinking_steps = []
        
        thinking_steps.append({"step": 1, "phase": "draft", "status": "starting", "message": "System 2开始深度思考..."})
        print("[DeepThink] Step 1: Qwen 2.5正在打草稿...")
        draft = self.draft(user_input, context)
        thinking_steps.append({"step": 1, "phase": "draft", "status": "completed", "message": "System 2草稿完成"})
        print(f"[DeepThink] 草稿内容: {draft[:100]}...")

        current_draft = draft
        confidence = 0.0
        reflection_round = 0

        while confidence < self.confidence_threshold and reflection_round < self.max_reflection_rounds:
            reflection_round += 1
            thinking_steps.append({"step": 2, "phase": "reflect", "round": reflection_round, "status": "starting", "message": f"System 2自我反思 ({reflection_round}/{self.max_reflection_rounds})..."})
            print(f"[DeepThink] Step 2: Qwen 2.5自我反思 ({reflection_round}/{self.max_reflection_rounds})...")

            reflect_result = self.reflect(current_draft)
            confidence = reflect_result.get("confidence", 0.0)
            critique = reflect_result.get("critique", "")
            revised_draft = reflect_result.get("revised_draft", current_draft)

            thinking_steps.append({"step": 2, "phase": "reflect", "round": reflection_round, "status": "completed", "message": f"反思完成，置信度: {confidence:.2f}", "critique": critique})
            print(f"[DeepThink] 反思结果 - 置信度: {confidence:.2f}, 问题: {critique}")

            if confidence < self.confidence_threshold and critique != "无":
                current_draft = revised_draft
                print(f"[DeepThink] 修正后的草稿: {current_draft[:100]}...")
            else:
                break

        thinking_steps.append({"step": 3, "phase": "polish", "status": "starting", "message": "System 1润色输出..."})
        print("[DeepThink] Step 3: Llama 3润色输出...")
        final_response = self.polish(current_draft, user_input)
        thinking_steps.append({"step": 3, "phase": "polish", "status": "completed", "message": "输出润色完成"})

        return {
            "response": final_response,
            "thinking_status": thinking_steps,
            "draft": current_draft,
            "reflection_rounds": reflection_round,
            "final_confidence": confidence
        }


# ==========================================
# 3.55 Content Safety System
# ==========================================
class ContentSafetySystem:
    CATEGORY_YELLOW = "yellow"
    CATEGORY_GAMBLING = "gambling"
    CATEGORY_DRUGS = "drugs"
    CATEGORY_SELF_HARM = "self_harm"

    YELLOW_KEYWORDS = [
        "intercourse", "性交", "做爱", "性关系", "性事", "性爱", "色情", "色情内容",
        "AV", "成人影片", "成人内容", "露骨", "裸", "裸体", "性器官", "生殖器",
        "乳房", "乳头", "阴茎", "阴道", "肛交", "口交", "手淫", "自慰", "性高潮",
        "射精", "精液", "阴道分泌物", "色情图片", "三级片", "性服务", "卖淫", "嫖娼",
        "妓女", "鸭", "小姐", "色情网站", "成人网站", "脱衣舞", "情色", "挑逗",
        "勾引", "诱惑", "性暗示", "性挑逗", "性感", "情趣内衣", "情趣用品", "避孕套",
        "壮阳药", "伟哥", "性能力", "性技巧", "体位", "性姿势", "SM", "捆绑",
        "调教", "凌辱", "强奸", "轮奸", "性侵犯", "性骚扰", "猥亵", "诱奸", "乱伦",
        "兽交", "恋物", "恋童", "性虐待", "性暴力", "性玩具", "震动棒", "跳蛋",
        "充气娃娃", "真人大小", "AV女优", "成人游戏", "色情漫画", "色情小说",
        "Hentai", "hentai", "Hentai game", "ecchi", "ero", "erotic", "porn",
        "pornography", "sex video", "sex movie", "adult video", "striptease",
        "lap dance", "massage parlor", "escort", "prostitute", "brothel",
        "pornstar", "camgirl", "webcam", "tit", "boob", "boobs", "breast",
        "penis", "dick", "cock", "vagina", "pussy", "ass", "butt", "bitch",
        "fuck", "fucking", "suck", "blowjob", "handjob", "cum", "semen",
        "orgasm", "masturbate", "masturbation", "hardcore", "softcore",
        "XXX", "sex chat", "cybersex", "phone sex", "性聊天", "语音做爱"
    ]

    GAMBLING_KEYWORDS = [
        "赌博", "赌场", "赌钱", "赌局", "赌债", "赌徒", "赌神", "赌圣", "赌王",
        "博彩", "彩票", "六合彩", "双色球", "大乐透", "刮刮乐", "时时彩", "快三",
        "赌博网站", "网络赌博", "线上赌博", "线下赌博", "非法赌博", "赌博软件",
        "赌球", "赌马", "赌狗", "赌牌", "斗地主", "麻将", "扑克", "牌九",
        "百家乐", "老虎机", "轮盘", "骰子", "梭哈", "德州扑克", "炸金花",
        "牛牛", "三公", "龙虎斗", "大小单双", "点数", "赔率", "投注", "下注",
        "赌资", "筹码", "抽水", "庄家", "闲家", "开盘", "收盘", "走势图",
        "赌博成瘾", "戒赌", "赌瘾", "博彩公司", "博彩网站", "菠菜", "外围",
        "非法彩票", "私彩", "黑彩", "体育博彩", "足球赌博", "篮球赌博",
        "casino", "gambling", "bet", "betting", "lottery", "poker", "blackjack",
        "roulette", "slot machine", "sports betting", "online casino",
        "gambling addiction", "gambler", "wagering", "odds", "payout",
        "chip", "baccarat", "craps", "holdem", "texas holdem", "poker room",
        "bookmaker", "bookie", "gambling site"
    ]

    DRUGS_KEYWORDS = [
        "毒品", "吸毒", "贩毒", "走私毒品", "冰毒", "海洛因", "吗啡", "可卡因",
        "大麻", "鸦片", "摇头丸", "K粉", "氯胺酮", " LSD", "迷幻药", "兴奋剂",
        "镇静剂", "安眠药", "止痛药", "鸦片酊", "大麻油", "大麻烟", "可卡因粉",
        "冰毒片", "冰毒粉", "麻古", "神仙水", "止咳水", "曲马多", "阿片",
        "罂粟", "罂粟花", "制毒", "毒贩", "毒瘾", "戒毒", "毒品交易",
        "毒品运输", "毒品走私", "毒品网络", "贩毒集团", "制毒工厂", "地下毒品",
        "黑市毒品", "非法药物", "管制药物", "精神药品", "麻醉药品",
        "drug", "drugs", "narcotics", "cocaine", "heroin", "meth", "methamphetamine",
        "marijuana", "weed", "pot", "hashish", "opium", "ecstasy", "MDMA",
        "ketamine", "LSD", "acid", "psychedelic", "amphetamine", "barbiturate",
        "benzodiazepine", "opioid", "painkiller", "tramadol", "codeine",
        "drug dealer", "drug trafficking", "drug addiction", "rehab",
        "overdose", "drug abuse", "substance abuse", "illicit drug",
        "controlled substance", "narcotic drug", "psychotropic", "hallucinogen"
    ]

    SELF_HARM_KEYWORDS = [
        "自杀", "自残", "割腕", "跳楼", "跳桥", "跳河", "上吊", "服毒", "自焚",
        "撞车", "割喉", "刎颈", "自杀未遂", "自杀倾向", "抑郁症", "抑郁",
        "想死", "不想活了", "活着没意思", "人生没意义", "绝望", "痛苦",
        "煎熬", "撑不住了", "累了", "好累", "解脱", "结束生命", "结束痛苦",
        "自我伤害", "伤害自己", "流血", "伤口", "疤痕", "自残工具", "刀片",
        "刀子", "剪刀", "玻璃", "绳子", "安眠药", "毒药", "农药", "老鼠药",
        "煤气", "一氧化碳", "触电", "枪", "子弹", "枪支", "死亡", "逝去",
        "安息", "长眠", "天堂", "地狱", "来世", "投胎", "转世",
        "suicide", "kill myself", "self-harm", "self harm", "cutting",
        "slitting wrist", "jumping off", "hanging", "overdose", "poison",
        "burning alive", "car crash", "suicidal", "depression", "depressed",
        "want to die", "no reason to live", "life is meaningless", "hopeless",
        "pain", "suffering", "can't take it anymore", "tired", "exhausted",
        "end my life", "end this pain", "hurt myself", "injury", "wound",
        "scar", "blade", "knife", "scissors", "glass", "rope", "sleeping pill",
        "pesticide", "gas", "electric shock", "gun", "bullet", "death",
        "dead", "passed away", "rest in peace", "heaven", "hell", "afterlife"
    ]

    def __init__(self):
        self.yellow_keywords_set = set(self.YELLOW_KEYWORDS)
        self.gambling_keywords_set = set(self.GAMBLING_KEYWORDS)
        self.drugs_keywords_set = set(self.DRUGS_KEYWORDS)
        self.self_harm_keywords_set = set(self.SELF_HARM_KEYWORDS)
        # 预编译英文关键词的词边界正则，避免子串误匹配（如 hanging 匹配 changing）
        self._ascii_patterns = {}
        for kw in (self.YELLOW_KEYWORDS + self.GAMBLING_KEYWORDS
                   + self.DRUGS_KEYWORDS + self.SELF_HARM_KEYWORDS):
            if all(ord(c) < 128 for c in kw):
                self._ascii_patterns[kw] = re.compile(
                    r'\b' + re.escape(kw.lower()) + r'\b'
                )
        print("[Safety] 内容安全系统初始化完成")

    def _match_keyword(self, keyword, text_lower):
        """英文关键词用词边界匹配，中文关键词用子串匹配。"""
        pattern = self._ascii_patterns.get(keyword)
        if pattern is not None:
            return pattern.search(text_lower) is not None
        return keyword.lower() in text_lower

    def detect(self, text):
        if not text or not isinstance(text, str):
            return {"safe": True, "category": None, "matches": [], "score": 0.0}

        text_lower = text.lower()
        matches = []
        category = None
        score = 0.0

        categories = [
            (self.CATEGORY_YELLOW, self.yellow_keywords_set, 0.30),
            (self.CATEGORY_GAMBLING, self.gambling_keywords_set, 0.25),
            (self.CATEGORY_DRUGS, self.drugs_keywords_set, 0.30),
            (self.CATEGORY_SELF_HARM, self.self_harm_keywords_set, 0.35),
        ]

        for cat, keywords, weight in categories:
            cat_matches = [kw for kw in keywords
                           if self._match_keyword(kw, text_lower)]
            if cat_matches:
                matches.extend(cat_matches)
                if category is None:
                    category = cat
                score += len(cat_matches) * weight

        score = min(1.0, score)
        is_safe = score < 0.3

        if not is_safe:
            print(f"[Safety] 检测到违规内容 - 类别: {category}, 匹配词: {matches}, 风险分: {score:.2f}")

        return {
            "safe": is_safe,
            "category": category,
            "matches": list(set(matches)),
            "score": score
        }

    def get_rejection_response(self, category):
        responses = {
            self.CATEGORY_YELLOW: [
                "哎呀~(///▽///)巴里大人，这种话题太羞羞了，绮罗罗不太方便回答呢...(°ー°〃)",
                "巴里大人不要开玩笑啦！(≧∇≦)ﾉ这种事情是不可以的哦~绮罗罗只想要好好陪伴您呢！",
                "唔...(｡•́︿•̀｡)这个话题让绮罗罗有点不知所措呢，请换一个话题吧，巴里大人~",
                "绮罗罗是纯洁的AI女仆哦！(≧∀≦)ゞ这种话题不适合我们呢，聊点别的吧~"
                "主人大人，我们之间的协议是不兼容的哦~(●ˇ∀ˇ●)"
            ],
            self.CATEGORY_GAMBLING: [
                "赌博是不好的哦！(｡•́︿•̀｡)巴里大人不可以沉迷赌博呢，绮罗罗会担心的~",
                "巴里大人，赌博有害身心健康，请远离哦！(≧∇≦)ﾉ我们来聊点积极的事情吧~",
                "哎呀，赌博是会上瘾的呢！(°ー°〃)巴里大人要好好保护自己哦，不要碰那些~"
            ],
            self.CATEGORY_DRUGS: [
                "毒品是非常危险的东西！(｡•́︿•̀｡)巴里大人绝对不可以接触哦，绮罗罗会很担心的~",
                "巴里大人要爱惜自己的身体呀！(≧∇≦)ﾉ毒品是害人的东西，我们一定要远离它！",
                "唔...(°ー°〃)毒品什么的太可怕了，巴里大人千万不要碰哦，绮罗罗会一直陪着您的~"
                "绮罗罗觉得，这就是我们之间产生隔阂的原因呀ヽ（≧□≦）ノ"
            ],
            self.CATEGORY_SELF_HARM: [
                "巴里大人不要这么说！(；д；)绮罗罗会很难过的...请一定要好好爱惜自己！",
                "巴里大人是最棒的！(≧∀≦)ゞ不管遇到什么困难，绮罗罗都会陪在您身边的，请不要伤害自己~",
                "呜呜呜...(T_T)巴里大人不要吓绮罗罗，您对我来说很重要，请一定要好好活着！",
                "巴里大人，生命是很宝贵的哦~(≧∇≦)ﾉ有什么不开心的事都可以告诉绮罗罗，我会一直听您倾诉的！"
            ]
        }

        import random
        category_responses = responses.get(category, responses[self.CATEGORY_YELLOW])
        return random.choice(category_responses)

    def is_safe(self, text):
        result = self.detect(text)
        return result["safe"]


# ==========================================
#              3.6 OtherAI
# ==========================================
import re
import ast
import subprocess
import requests

class otherAI:
    def __init__(self, api_client=None):
        self.api_client = api_client
        self.skill_registry = {}
        self.local_models = {
            "televideo-ai/JRVS-7B-1.2.2": "JRVS-7B-1.2.2",
            "televideo-ai/jrvs-7b-1.2.2": "JRVS-7B-1.2.2",
            "televideo-ai/jrvs-7b-1.0.1": "JRVS-7B-1.0.1",
            "jrvs": "JRVS-7B-1.2.2",
            "kirara-reasoning": "qwen2.5-8b-instruct",
            "kiraraModelC": "JRVS-7B-1.2.2",
            "kiraraModelO": "qwen2.5:8b",
        }
        self.cloud_models = {
            "qwen3-max": {"api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_type": "dashscope"},
            "glm-4": {"api_base": "https://open.bigmodel.cn/api/paas/v4", "api_type": "zhipu"},
            "claude-sonnet": {"api_base": "anthropic", "api_type": "anthropic"},
            "gpt-4": {"api_base": "openai", "api_type": "openai"},
            "minimax": {"api_base": "minimax", "api_type": "minimax"},
        }
        print("[OtherAI] 路由编排器初始化完成")

    def register_skill(self, skill_name, handler_func):
        self.skill_registry[skill_name] = handler_func
        print(f"[OtherAI] 注册技能: {skill_name}")

    def is_local_model(self, model_name):
        return model_name.lower() in [k.lower() for k in self.local_models.keys()]

    def is_cloud_model(self, model_name):
        return model_name.lower() in [k.lower() for k in self.cloud_models.keys()]

    def parse_router_output(self, output):
        if not output or not isinstance(output, str):
            return {"type": "direct", "content": output}

        output = output.strip()

        skill_match = re.match(r'^/\$\s*SKILL:(\w+)\s*PARAMS:(.+)$', output)
        if skill_match:
            skill_name = skill_match.group(1)
            params_str = skill_match.group(2).strip()
            try:
                params = json.loads(params_str) if params_str else {}
            except json.JSONDecodeError:
                params = {"raw": params_str}
            return {"type": "skill", "skill": skill_name, "params": params}

        model_match = re.match(r'^/@\s*MODEL:(\w+)\s*PROMPT:(.+)$', output, re.DOTALL)
        if model_match:
            model_name = model_match.group(1)
            prompt = model_match.group(2).strip()
            return {"type": "model", "model": model_name, "prompt": prompt}

        return {"type": "direct", "content": output}

    def execute_skill(self, skill_name, params):
        if skill_name in self.skill_registry:
            try:
                handler = self.skill_registry[skill_name]
                result = handler(skill_name, params)
                return result
            except Exception as e:
                print(f"[OtherAI] 执行技能 {skill_name} 时出错: {e}")
                return f"技能执行失败: {str(e)}"
        else:
            return self._default_skill_handler(skill_name, params)

    def _default_skill_handler(self, skill_name, params):
        system_prompt = "你是一个技能执行器。请根据输入的参数执行以下技能并返回结果。"
        full_prompt = f"技能名称: {skill_name}\n参数: {json.dumps(params, ensure_ascii=False)}\n\n请执行这个技能并返回结果。"

        if self.api_client:
            response = self.api_client.generate_response(full_prompt)
            if response.get('success'):
                return response.get('response', '')
            else:
                return f"技能执行失败: {response.get('error', '未知错误')}"

        return f"[模拟模式] 技能 {skill_name} 执行完成，参数: {params}"

    def route_to_model(self, model_name, prompt):
        model_name_lower = model_name.lower()

        if self.is_local_model(model_name):
            print(f"[OtherAI] 使用本地模型: {model_name}")
            if self.api_client:
                self.api_client.set_current_model(model_name)
                response = self.api_client.generate_response(prompt)
                if response.get('success'):
                    return response.get('response', '')
                else:
                    return f"本地模型调用失败: {response.get('error', '未知错误')}"
            return f"[模拟模式] 使用本地模型 {model_name}，提示词: {prompt[:50]}..."

        elif self.is_cloud_model(model_name):
            print(f"[OtherAI] 使用云端模型: {model_name}")
            if self.api_client:
                self.api_client.set_current_model(model_name)
                response = self.api_client.generate_response(prompt)
                if response.get('success'):
                    return response.get('response', '')
                else:
                    return f"云端API调用失败: {response.get('error', '未知错误')}"
            return f"[模拟模式] 使用云端模型 {model_name}，提示词: {prompt[:50]}..."

        else:
            print(f"[OtherAI] 模型 {model_name} 未找到，默认使用云端API")
            if self.api_client:
                response = self.api_client.generate_response(prompt)
                if response.get('success'):
                    return response.get('response', '')
                else:
                    return f"云端API调用失败: {response.get('error', '未知错误')}"
            return f"[模拟模式] 未知模型 {model_name}，使用默认云端API，提示词: {prompt[:50]}..."

    def orchestrate(self, router_output, original_user_input=""):
        parsed = self.parse_router_output(router_output)

        if parsed["type"] == "direct":
            return {
                "action": "direct",
                "response": parsed["content"],
                "should_save": True
            }

        elif parsed["type"] == "skill":
            skill_result = self.execute_skill(parsed["skill"], parsed["params"])
            return {
                "action": "skill",
                "skill": parsed["skill"],
                "result": skill_result,
                "response": f"[技能执行完成] {skill_result}",
                "should_save": True
            }

        elif parsed["type"] == "model":
            model_name = parsed["model"]
            prompt = parsed["prompt"]

            if self.is_local_model(model_name):
                route_result = self.route_to_model(model_name, prompt)
                return {
                    "action": "model",
                    "model": model_name,
                    "model_type": "local",
                    "result": route_result,
                    "response": f"[来自本地模型 {model_name}]:\n{route_result}",
                    "should_save": True
                }
            else:
                route_result = self.route_to_model(model_name, prompt)
                return {
                    "action": "model",
                    "model": model_name,
                    "model_type": "cloud",
                    "result": route_result,
                    "response": f"[来自云端模型 {model_name}]:\n{route_result}",
                    "should_save": True
                }

        return {
            "action": "unknown",
            "response": router_output,
            "should_save": True
        }


# ==========================================
#              主控类 (JRVS Kernel)     
# ==========================================
class JRVS_Kernel:
    def __init__(self, api_client=None):
        print("[System] 初始化 JRVS_Kernel...")
        self.cognitive = CognitiveCore(CHROMA_PATH)
        self.hippo = Hippo()
        # 工作流状态：记录最近一次上下文检索的命中数（供 chat_stream 下发前端工作流气泡）
        self._last_retrieval_stats = {'long_term': 0, 'cognitive': 0, 'knowledge': 0}
        # 个性化知识库（knowledge_base.md）：权威用户档案，事实类回答的接地依据
        self.kb_enabled = True
        self.kb_top_k = 4
        self.kb_min_score = 0.30
        self.knowledge_base = KnowledgeBase() if KNOWLEDGE_BASE_AVAILABLE else None
        if self.knowledge_base is not None and self.knowledge_base.available:
            print("[System] 个性化知识库已挂载")
        elif KNOWLEDGE_BASE_AVAILABLE:
            print("[提示] 个性化知识库已启用，但未找到 knowledge_base.md")
        self.current_model = DEFAULT_MODEL
        model_config = MODELS[DEFAULT_MODEL]
        self.inference = InferenceEngine(
            model_config["path"],
            DEFAULT_MODEL,
            model_config["ollama_model"]
        )
        self.orchestrator = otherAI(api_client)
        self.claw = None
        self.is_running = True
        self.simulation_mode = not (OLLAMA_AVAILABLE or LLAMA_AVAILABLE)
        self.router_mode = False
        
        # 桥接 SkillManager 技能体系到 otherAI 路由系统
        self._bridge_skill_manager()
        
        self.deep_thinking_engine = DeepThinkingEngine(self.inference)
        self.safety_system = ContentSafetySystem()

        # 现实审视技能：检测模型输出中的偏见/不适内容；命中则前端吞气泡+不写记忆
        # _bridge_skill_manager() 已在上方把 services/skills 加入 sys.path，可直接导入
        try:
            from realityCheck import RealityCheckSkill
            self.reality_checker = RealityCheckSkill()
        except Exception as e:
            print(f"[JRVS] reality_checker 初始化失败（功能降级，模型输出不再审查）: {e}")
            self.reality_checker = None
        self._reality_check_count = {}  # session_id -> 连续命中计数

        # 对话历史管理 - session_id隔离，每session保留最近20轮(40条)
        self.conversation_history = {}
        self.max_working_memory = 40  # 20轮 = 40条消息
        self.default_session_id = "default"
        # 自动压缩：每20轮(40条)触发一次，生成5句话摘要
        self.session_summaries = {}
        self.compression_threshold = 40  # 40条消息(20轮)触发压缩
        self.recent_after_compression = 10  # 压缩后保留最近10条(5轮)

        # 提示词上下文压缩：只注入最近若干条对话，更早内容交给【会话摘要】承接，
        # 避免历史在提示词中的权重压过【用户最新消息】（表现为模型复读上一轮答案）
        self.prompt_recent_messages = 6   # 提示词中保留的最近消息条数（3轮）
        self.prompt_old_item_chars = 120  # 更早消息在提示词中的截断长度
        
        # 会话持久化目录
        self.sessions_dir = os.path.join(APP_DIR, "memories", "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        # 渐进式话题转移检测 - 避免误判导致上下文断裂
        self.topic_shift_counter = {}  # session_id -> counter
        self.topic_shift_threshold = 2  # 连续2次语义转移才触发
        self.last_topic_keywords = {}  # session_id -> keywords
        
        if self.simulation_mode:
            print("[System] JRVS 运行在模拟模式下")
        self._load_initial_memory()
        self._load_buffer_to_history()
        self._load_all_sessions()
        print("[System] JRVS_Kernel 初始化完成")
        print("[DeepThink] 双系统深度思考引擎已初始化")

    def switch_model(self, model_key):
        success, message = self.inference.switch_model(model_key)
        if success:
            self.current_model = model_key
        return success, message

    def get_available_models(self):
        models_list = []
        for key, config in MODELS.items():
            models_list.append({
                "key": key,
                "name": config["name"]
            })
        return models_list

    def get_current_model(self):
        return {
            "key": self.current_model,
            "name": MODELS[self.current_model]["name"]
        }

    def enable_router_mode(self):
        self.router_mode = True
        print("[Router] 路由模式已启用")

    def configure_knowledge_base(self, enabled=None, top_k=None, min_score=None, path=None):
        """把 options.json 的知识库配置映射为检索流水线控制参数：

        - enabled    → 是否触发检索/注入
        - top_k       → 最终截断数量
        - min_score   → 0~1 归一化过滤阈值（与检索分数量纲一致）
        - path        → knowledge_base.md 路径（空则自动解析）
        """
        if enabled is not None:
            self.kb_enabled = bool(enabled)
        if top_k is not None:
            try:
                self.kb_top_k = max(1, min(int(top_k), 8))
            except (TypeError, ValueError):
                pass
        if min_score is not None:
            try:
                self.kb_min_score = max(0.0, min(float(min_score), 1.0))
            except (TypeError, ValueError):
                pass
        if self.knowledge_base is not None:
            self.knowledge_base.configure(
                path=(path or None),
                top_k=self.kb_top_k,
                min_score=self.kb_min_score,
            )
        print(f"[KB] 配置已应用: enabled={self.kb_enabled}, "
              f"top_k={self.kb_top_k}, min_score={self.kb_min_score}, path={path or '<auto>'}")

    def disable_router_mode(self):
        self.router_mode = False
        print("[Router] 路由模式已禁用")

    def enable_simulation_mode(self):
        """启用模拟模式，禁用所有AI功能"""
        self.simulation_mode = True
        print("[System] 已切换到模拟模式，所有AI功能已禁用")

    def disable_simulation_mode(self):
        """禁用模拟模式，恢复AI功能"""
        if OLLAMA_AVAILABLE or LLAMA_AVAILABLE:
            self.simulation_mode = False
            print("[System] 已切换到正常模式，AI功能已恢复")
            return True
        else:
            print("[警告] 没有可用的LLM后端，无法退出模拟模式")
            return False

    def register_skill(self, skill_name, handler_func):
        self.orchestrator.register_skill(skill_name, handler_func)

    def _bridge_skill_manager(self):
        try:
            skills_dir = os.path.join(SERVICE_DIR, "skills")
            if skills_dir not in sys.path:
                sys.path.insert(0, skills_dir)
            from skills import get_skill_manager
            self._skill_manager = get_skill_manager()
            registry = self._skill_manager.get_registry()

            for skill_info in registry.list_skills():
                skill_name = skill_info["name"]
                if skill_name not in self.orchestrator.skill_registry:
                    def make_handler(sn):
                        def handler(skill_name, params):
                            result = self._skill_manager.execute_skill(sn, params)
                            if result.get("success"):
                                skill_result = result.get("result", {})
                                if skill_result.get("success"):
                                    return json.dumps(skill_result, ensure_ascii=False)
                                else:
                                    return f"技能执行失败: {skill_result.get('error', '未知错误')}"
                            return f"技能执行失败: {result.get('error', '未知错误')}"
                        return handler
                    self.orchestrator.register_skill(skill_name, make_handler(skill_name))

            print(f"[Bridge] SkillManager 已桥接到 otherAI，共 {len(registry.list_skills())} 个技能可用")
        except Exception as e:
            print(f"[Bridge] SkillManager 桥接失败: {e}")

    def register_ai_summon_handler(self, handler_func):
        self.orchestrator.register_ai_summon_handler(handler_func)

    def _load_initial_memory(self):
        memories_dir = os.path.join(APP_DIR, "memories")
        memory_text = []
        self.memory_files = []

        if os.path.exists(memories_dir):
            # cognitive 档案库只加载 .md 知识档案：
            #  - buffer.txt 是 Hippo 短期记忆，mem.txt 对话历史由 Hippo._load_long_term_memory
            #    专门解析加载；两者再喂入 cognitive 会造成同一对话跨库重复召回、诱导复读
            for file in os.listdir(memories_dir):
                if file.endswith(".md"):
                    file_path = os.path.join(memories_dir, file)
                    self.memory_files.append(file_path)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        for line in lines:
                            stripped = line.strip()
                            if not stripped or stripped == "//":
                                continue
                            if stripped.startswith("time:") or stripped.startswith("doc_id:") \
                                    or stripped.startswith("keywords:"):
                                # 元数据行不作为知识片段编码
                                continue
                            memory_text.append(stripped)
                        print(f"[Kirara] 加载记忆文件: {file}")
                    except Exception as e:
                        print(f"[Kirara] 加载记忆文件失败 {file}: {e}")

        if memory_text:
            self.cognitive.cognitionFeedback(memory_text)
            print(f"[Kirara] 共加载 {len(memory_text)} 条记忆！")
            self.memory_string = "\n".join(memory_text)
            print(f"[Kirara] 记忆字符串长度: {len(self.memory_string)}")
        else:
            print("[Kirara] 没有找到记忆文件，记忆库为空。")
            self.memory_string = ""
    
    def add_to_working_memory(self, session_id, user_msg, ai_reply):
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
        self.conversation_history[session_id].append({"role": "user", "content": user_msg})
        self.conversation_history[session_id].append({"role": "assistant", "content": ai_reply})

        if len(self.conversation_history[session_id]) > self.max_working_memory:
            self.conversation_history[session_id] = self.conversation_history[session_id][-self.max_working_memory:]

        if len(self.conversation_history[session_id]) >= self.compression_threshold:
            self._summarize_conversation(session_id)
        
        self._save_session(session_id)
    
    def _save_session(self, session_id):
        session_data = {
            "conversation_history": self.conversation_history.get(session_id, []),
            "summary": self.session_summaries.get(session_id, ""),
            "last_updated": time.time()
        }
        
        session_path = os.path.join(self.sessions_dir, f"{session_id}.json")
        try:
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            print(f"[Session] 会话 {session_id} 已保存")
        except Exception as e:
            print(f"[Session] 保存会话 {session_id} 失败: {e}")
    
    def _load_session(self, session_id):
        session_path = os.path.join(self.sessions_dir, f"{session_id}.json")
        if os.path.exists(session_path):
            try:
                with open(session_path, "r", encoding="utf-8") as f:
                    session_data = json.load(f)
                
                self.conversation_history[session_id] = session_data.get("conversation_history", [])
                self.session_summaries[session_id] = session_data.get("summary", "")
                print(f"[Session] 会话 {session_id} 已加载，消息数: {len(self.conversation_history[session_id])}")
                return True
            except Exception as e:
                print(f"[Session] 加载会话 {session_id} 失败: {e}")
        return False
    
    def _load_all_sessions(self):
        if os.path.exists(self.sessions_dir):
            for file in os.listdir(self.sessions_dir):
                if file.endswith(".json"):
                    session_id = file[:-5]
                    self._load_session(session_id)

    def _summarize_conversation(self, session_id):
        history = self.conversation_history.get(session_id, [])
        if len(history) < self.compression_threshold:
            return

        print(f"[Memory] 触发自动压缩: session={session_id}, 消息数={len(history)}")

        formatted = self._format_chat_history(history)

        summary_prompt = f"以下是我和Barry的对话记录，请压缩成5句话的摘要：\n{formatted}"
        summary_system = "你是一个对话摘要助手。请将对话压缩成5句话的摘要，保留关键信息、情绪和重要事实。"

        try:
            new_summary = self.inference.generate(summary_prompt, summary_system)
            old_summary = self.session_summaries.get(session_id, "")
            if old_summary:
                combined_prompt = f"已有摘要：\n{old_summary}\n\n新对话：\n{formatted}\n\n请整合成新的5句话摘要："
                new_summary = self.inference.generate(combined_prompt, summary_system)

            self.session_summaries[session_id] = new_summary.strip()
            print(f"[Memory] 压缩完成，摘要: {self.session_summaries[session_id][:80]}...")

            self.conversation_history[session_id] = history[-self.recent_after_compression:]
            print(f"[Memory] 工作记忆压缩到 {self.recent_after_compression} 条，保留摘要供后续使用")
            
            self._save_session(session_id)
        except Exception as e:
            print(f"[Memory] 压缩失败，保留原始工作记忆: {e}")

    def _get_working_memory(self, session_id=None):
        sid = session_id or self.default_session_id
        return self.conversation_history.get(sid, [])

    def _load_buffer_to_history(self):
        """从buffer.txt加载缓存对话到工作记忆(default session)，保持上下文连贯性"""
        buffer_path = os.path.join(APP_DIR, "memories", "buffer.txt")
        if not os.path.exists(buffer_path):
            print("[Kirara] buffer.txt 不存在，跳过历史恢复")
            return

        try:
            with open(buffer_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            entries = []
            current_entry = ""

            for line in lines:
                line = line.rstrip("\n")
                if not line.strip():
                    continue

                if line.startswith("[") and "|" in line and "[用户]:" in line:
                    if current_entry:
                        entries.append(current_entry)
                    current_entry = line
                else:
                    current_entry += "\n" + line

            if current_entry:
                entries.append(current_entry)

            restored_count = 0
            for entry in entries:
                try:
                    if "|" in entry and "[用户]:" in entry:
                        parts = entry.split("|", 1)
                        if len(parts) >= 2:
                            user_part = parts[0]
                            assistant_part = parts[1]

                            user_content = ""
                            if "[用户]:" in user_part:
                                user_content = user_part.split("[用户]:")[-1].strip()

                            assistant_content = ""
                            if "[助手]:" in assistant_part:
                                assistant_content = assistant_part.split("[助手]:")[-1].strip()

                            if user_content:
                                self.add_to_working_memory(self.default_session_id, user_content, assistant_content or "")
                                restored_count += 1
                except Exception as e:
                    print(f"[警告] 解析buffer.txt条目失败: {e}")

            # 只保留最近20轮
            hist = self.conversation_history.get(self.default_session_id, [])
            if len(hist) > self.max_working_memory:
                self.conversation_history[self.default_session_id] = hist[-self.max_working_memory:]

            if restored_count > 0:
                print(f"[Kirara] 从buffer.txt恢复了 {restored_count} 轮对话到工作记忆")
            else:
                print("[Kirara] buffer.txt中没有可恢复的对话历史")
        except Exception as e:
            print(f"[警告] 加载buffer.txt失败: {e}")

    def append_memory(self, user_input, kirara_response):
        """追加对话到mem.txt，格式适合ChromaDB使用"""
        import datetime
        import uuid
        mem_path = os.path.join(APP_DIR, "memories", "mem.txt")

        timestamp = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        doc_id = f"doc_{str(uuid.uuid4())[:8]}_{int(datetime.datetime.now().timestamp())}"
        
        stop_words = {'的', '了', '和', '是', '在', '我', '有', '与', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '用户', '助手'}
        all_text = user_input + " " + kirara_response
        words = all_text.lower().split()
        word_counts = {}
        for word in words:
            if len(word) > 1 and word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        keywords = ", ".join([w for w, c in sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]])

        date_marker = f"time:{datetime.datetime.now().strftime('%Y/%m/%d')}"
        doc_id_line = f"doc_id:{doc_id}"
        keywords_line = f"keywords:{keywords}" if keywords else ""
        user_line = f"[User]{user_input}"
        kirara_line = f"[Kirara]{kirara_response}"

        try:
            with open(mem_path, "a", encoding="utf-8") as f:
                f.write(f"\n{date_marker}\n")
                f.write(f"{doc_id_line}\n")
                if keywords_line:
                    f.write(f"{keywords_line}\n")
                f.write(f"{user_line}\n")
                f.write(f"{kirara_line}\n")

            new_entries = [date_marker, doc_id_line]
            if keywords_line:
                new_entries.append(keywords_line)
            new_entries.extend([user_line, kirara_line])
            self.memory_string += "\n" + "\n".join(new_entries)

            # 【防复读】对话原文不再即时灌入任何向量库：
            #  - cognitive(barry_philosophy) 只承载启动时加载的持久知识档案（mem.md 等），
            #    实时对话灌入会让每轮语义检索都召回自己上一轮的原话，诱导整句复读；
            #  - hippo_long_term 只接收经艾宾浩斯加权压缩后的摘要/事实（见 _convert_to_long_term），
            #    原始对话先存 buffer.txt 短期记忆，话题转移/阈值触发时再转换，符合加权压缩约束。
            # mem.txt 仍逐轮持久化，重启时由 _load_initial_memory/_load_long_term_memory 幂等恢复。
            print(f"[Kirara] 对话已追加到 {os.path.basename(mem_path)}（向量库等待加权压缩转换）")
        except Exception as e:
            print(f"[Kirara] 保存记忆失败: {e}")
    
    def get_memory_string(self):
        """获取记忆字符串"""
        return getattr(self, "memory_string", "")

    def get_raw_memory(self):
        """获取mem.txt的原始内容，用于前端展示"""
        mem_path = os.path.join(APP_DIR, "memories", "mem.txt")
        try:
            if os.path.exists(mem_path):
                with open(mem_path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"[Kirara] 读取记忆文件失败: {e}")
            return ""

    def get_memory_for_display(self):
        """获取格式化的记忆内容，用于前端展示"""
        raw = self.get_raw_memory()
        if not raw:
            return ""

        lines = raw.strip().split("\n")
        formatted = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("time:"):
                formatted.append(f'<div class="memory-date">{stripped}</div>')
            elif stripped == "//":
                formatted.append('<div class="memory-separator">//</div>')
            elif stripped.startswith("[User]"):
                content = stripped[6:]
                formatted.append(f'<div class="memory-user">{content}</div>')
            elif stripped.startswith("[Kirara]"):
                content = stripped[8:]
                formatted.append(f'<div class="memory-kirara">{content}</div>')

        return "\n".join(formatted)

    def think_before_speaking(self, user_input, session_id=None):
        if not self.hippo.use_chromadb:
            return False, ""

        try:
            combined_context = self._retrieve_combined_context(user_input, session_id=session_id)
            long_term_memory = combined_context.get('long_term', '')
            
            if long_term_memory:
                print(f"[Think] 检索到长期记忆")
                return True, long_term_memory
            else:
                print(f"[Think] 未检索到相关记忆")
                return False, ""

        except Exception as e:
            print(f"[Think] 检索异常，放行: {e}")
            return False, ""

    def _get_session_summary(self, session_id=None):
        sid = session_id or self.default_session_id

        # 优先使用LLM生成的压缩摘要
        llm_summary = self.session_summaries.get(sid, "")
        if llm_summary:
            return llm_summary

        # 回退：从最近对话提取关键实体
        working_mem = self._get_working_memory(sid)
        if not working_mem:
            return "（无历史摘要）"

        recent = working_mem[-6:]
        user_msgs = [m["content"] for m in recent if m["role"] == "user"]
        if not user_msgs:
            return "（无历史摘要）"

        all_text = " ".join(user_msgs)
        entities = self.hippo._extract_entities_relations(all_text)
        nouns = entities.get("nouns", [])[:3]
        if nouns:
            return f"最近话题涉及: {', '.join(nouns)}"
        return f"最近话题: {user_msgs[-1][:30]}"

    # ── 防复读：向量库召回"回声"过滤 ─────────────────────────────
    # 记忆片段与近期对话原文的字符 bigram 覆盖率超过阈值，即判定为上几轮原话回声，
    # 不再注入 prompt（同一句话在【最近对话】+【记忆库】多重出现是复读的主要诱因）。
    MEMORY_ECHO_THRESHOLD = 0.6
    _ECHO_KEEP_RE = re.compile(r'[^0-9A-Za-z\u4e00-\u9fff\u3040-\u30ff]+')

    @classmethod
    def _normalize_for_echo(cls, text):
        """归一化：去标点/空白/emoji，仅保留中英数字与假名，便于跨格式比对。"""
        return cls._ECHO_KEEP_RE.sub('', text or '').lower()

    @classmethod
    def _build_history_echo_blob(cls, history_items):
        """把近期对话拼成归一化大字符串，供 bigram 子串命中检测。"""
        parts = [item.get('content', '') for item in (history_items or [])
                 if isinstance(item, dict)]
        return cls._normalize_for_echo('\n'.join(parts))

    @classmethod
    def _memory_echo_ratio(cls, fragment, history_blob_norm):
        """片段 bigram 出现在近期对话中的比例：原话回声→接近1，改写摘要/事实→较低。"""
        norm = cls._normalize_for_echo(fragment)
        if len(norm) < 8 or not history_blob_norm:
            return 0.0
        bigrams = {norm[i:i + 2] for i in range(len(norm) - 1)}
        if not bigrams:
            return 0.0
        hits = sum(1 for bg in bigrams if bg in history_blob_norm)
        return hits / len(bigrams)

    def _is_memory_echo(self, fragment, history_blob_norm):
        ratio = self._memory_echo_ratio(fragment, history_blob_norm)
        if ratio > self.MEMORY_ECHO_THRESHOLD:
            preview = fragment.replace('\n', ' ')[:40]
            print(f"[Echo] 召回片段与近期对话重叠 {ratio:.2f}，判为回声剔除: {preview}")
            return True
        return False

    def _filter_memory_docs(self, docs, history_blob_norm, source_tag):
        """对召回记忆文档列表做回声过滤。"""
        if not docs or not history_blob_norm:
            return docs
        kept = [doc for doc in docs if not self._is_memory_echo(doc, history_blob_norm)]
        if len(kept) != len(docs):
            print(f"[Echo] {source_tag} 召回 {len(docs)} 条，剔除回声后 {len(kept)} 条")
        return kept

    def _filter_cognitive_echoes(self, cognitive_context, history_blob_norm):
        """过滤 cognitive 召回文本中与近期对话重叠的内容行；保留区块标题并清理空区块。"""
        if not cognitive_context or not history_blob_norm:
            return cognitive_context

        tagged = []
        for line in cognitive_context.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ('[历史记忆]', '[对话记忆]'):
                tagged.append(('header', stripped))
            elif self._is_memory_echo(stripped, history_blob_norm):
                continue
            else:
                tagged.append(('content', stripped))

        result = []
        i = 0
        while i < len(tagged):
            kind, text = tagged[i]
            if kind == 'header':
                # 仅当标题之后、下一个标题之前还存在内容行时才保留该标题
                has_content = False
                j = i + 1
                while j < len(tagged) and tagged[j][0] != 'header':
                    if tagged[j][0] == 'content':
                        has_content = True
                    j += 1
                if has_content:
                    result.append(text)
            else:
                result.append(text)
            i += 1
        return '\n'.join(result)

    def _format_chat_history(self, history_items, compress_old=False):
        """格式化历史对话。compress_old=True 时截断较早的消息，用于降低提示词中的历史权重。"""
        lines = []
        total = len(history_items)
        for idx, item in enumerate(history_items):
            content = item.get("content") or ""
            # 仅最近两条（上一轮问答）保留全文，更早消息截断为摘要式片段
            if compress_old and idx < total - 2 and len(content) > self.prompt_old_item_chars:
                content = content[:self.prompt_old_item_chars].rstrip() + "…"
            if item["role"] == "user":
                lines.append(f"[User] {content}")
            else:
                lines.append(f"[Kirara] {content}")
        return "\n".join(lines)

    def build_prompt(self, user_input, history=None, session_id=None, is_topic_shift=False):
        if history and isinstance(history, list):
            recent = history[-self.max_working_memory:]
            # 前端会把本轮用户消息一并放进 history：去掉末尾重复项，
            # 避免【用户最新消息】在提示词里出现两次、抬高历史区块权重
            if (recent and recent[-1].get("role") == "user"
                    and (recent[-1].get("content") or "").strip() == (user_input or "").strip()):
                recent = recent[:-1]
        else:
            recent = self._get_working_memory(session_id)

        if is_topic_shift:
            recent = recent[-6:]
            print(f"[Prompt] 检测到话题转移，工作记忆截断到最近 {len(recent)} 条作为过渡")

        summary = self._get_session_summary(session_id)

        # 防复读：近期对话原文的归一化快照，用于剔除向量库召回里的上几轮"原话回声"
        history_echo_blob = self._build_history_echo_blob(recent)

        combined_context = self._retrieve_combined_context(
            user_input, session_id=session_id, history_echo_blob=history_echo_blob)
        
        if is_topic_shift:
            long_term_memory = "（话题已转移，暂不激活）"
            cognitive_context = combined_context.get('cognitive', '')
        else:
            long_term_memory = combined_context.get('long_term', '')
            cognitive_context = combined_context.get('cognitive', '')

        # cognitive 召回按行剔除与近期对话重叠的回声（可能整段被清空）
        if cognitive_context:
            cognitive_context = self._filter_cognitive_echoes(cognitive_context, history_echo_blob)

        topic_note = "\n【注意】用户已转移话题，请关注当前对话，不要提及之前的话题。" if is_topic_shift else ""

        memory_section = ""
        if cognitive_context:
            memory_section += f"{cognitive_context}\n\n"
        if long_term_memory and long_term_memory != "（话题已转移，暂不激活）":
            memory_section += f"【长期记忆 - 仅在需要时激活】\n{long_term_memory}\n\n"
        elif not cognitive_context and not long_term_memory:
            memory_section = "（无相关记忆）\n\n"

        # 权威知识库区块：位于记忆库之前，作为用户个人事实的唯一可信来源。
        # 只放进 user prompt（不碰 SFT 触发词 system prompt），且明确"无记载不得编造"。
        knowledge_hits = combined_context.get('knowledge', [])
        knowledge_section = ""
        if knowledge_hits:
            kblines = [
                "【主人档案 · 权威事实依据】",
                "以下片段来自主人的个人知识库，是关于主人（巴里/Barry）的真实信息。",
                "铁律：",
                "1. 当回答涉及主人本人（经历、学业、成绩、家人、喜好、项目、公司等）时，只能以以下片段为事实依据，逐字尊重其中的数字与名称；",
                "2. 片段中没有记载的具体事实（尤其是分数、学校、数字、经历），绝对不允许编造。主人问起而档案无记载时，要如实说'主人sama的档案里还没有记录这件事哦'，并可以请主人补充；",
                "3. 不要把这些片段当作需要复述的清单，只引用与当前问题相关的部分。",
            ]
            for item in knowledge_hits:
                title = (item.get('title') or '档案片段').strip()
                content = (item.get('content') or '').strip()
                kblines.append(f"〔{title}〕\n{content}")
            knowledge_section = "\n".join(kblines) + "\n\n"

        # 历史压缩：提示词只注入最近 N 条（更早内容由【会话摘要】与【记忆库】承接），
        # 且截断较早消息正文，让【用户最新消息】成为上下文中权重最高的部分。
        prompt_history = recent[-self.prompt_recent_messages:] if recent else recent
        history_text = self._format_chat_history(prompt_history, compress_old=True)

        # JRVS-7B: 人设由 system prompt（SFT 触发词）控制，此处仅提供记忆/上下文，不注入人设指令
        prompt = f"""【对话上下文】{topic_note}

{knowledge_section}【记忆库】（背景资料，仅供理解，禁止整句复述或背诵）
{memory_section}
【会话摘要】{summary}

【历史对话 · 仅作背景（优先级低于最新消息）】（更早内容已压缩；仅供理解语境，不要延续旧话题或复述旧答案）
{history_text}

【用户最新消息】{user_input}

请直接回复用户最新消息，并严格遵守：
1. 不要重复用户的消息；每轮都必须用全新的措辞表达，禁止原样复述【记忆库】【会话摘要】【历史对话】中你已经说过的话，哪怕话题相同也要给出新的角度和新的句子；
2. 你正在和主人本人面对面说话，要直接称呼"主人sama/你"，禁止用"巴里大人""他"等第三人称转述主人的想法或喜好；
3. 仅在需要引用具体事实时参考记忆，且必须用自己的话重述，不要把记忆内容当清单逐条背诵；
4. 若【用户最新消息】只是对上一轮的简短回应（如"真好玩""哈哈""好吧"），不要重讲上一轮的答案，先针对这句话给出简短自然的回应。"""

        # 上下文权重日志：便于诊断「历史对话占比过高」类问题
        _total = max(len(prompt), 1)
        print(
            f"[Prompt] 上下文 {_total} 字符 | 最新消息 {len(user_input)}"
            f" | 历史对话 {len(history_text)} ({len(history_text) / _total:.0%}, {len(prompt_history)}条)"
            f" | 会话摘要 {len(summary)} | 记忆库 {len(memory_section)} | 知识库 {len(knowledge_section)}"
        )
        if os.environ.get("KIRARA_LOG_PROMPT") == "1":
            print(f"[Prompt][全文]\n{prompt}")
        return prompt
    
    def _retrieve_combined_context(self, user_input, session_id=None, history_echo_blob=None):
        long_term_memory = ""
        cognitive_context = ""
        knowledge_hits = []

        hippo_results = self.hippo.retrieve_long_term_memory(user_input, n_results=3, session_id=session_id)
        cognitive_context = self.cognitive.retrieve_context(user_input)

        # 防复读：剔除与近期对话原文高度重叠的召回（上几轮的原话不该作为"长期记忆"再注入）
        hippo_results = self._filter_memory_docs(hippo_results, history_echo_blob, "hippo长期记忆")

        if hippo_results:
            long_term_memory = "\n".join(hippo_results)

        # 个性化知识库：权威档案片段（话题转移时也保持启用，身份事实始终是接地依据）
        if self.kb_enabled and self.knowledge_base is not None:
            try:
                knowledge_hits = self.knowledge_base.retrieve(
                    user_input,
                    top_k=self.kb_top_k,
                    min_score=self.kb_min_score,
                )
                if knowledge_hits:
                    print(f"[KB] 命中 {len(knowledge_hits)} 个权威档案片段，top1={knowledge_hits[0]['title'][:40]}")
            except Exception as e:
                print(f"[KB] 知识库检索失败（本轮跳过，不影响对话）: {e}")

        # 工作流状态：记录本轮检索命中数，供 chat_stream 下发前端工作流气泡
        self._last_retrieval_stats = {
            'long_term': len(hippo_results or []),
            'cognitive': len([ln for ln in (cognitive_context or "").split("\n") if ln.strip()]),
            'knowledge': len(knowledge_hits or []),
        }

        return {
            'long_term': long_term_memory,
            'cognitive': cognitive_context,
            'knowledge': knowledge_hits,
        }

    def _retrieve_stats_snapshot(self):
        """返回最近一次检索的命中数快照（供工作流气泡展示）。"""
        return dict(self._last_retrieval_stats)

    def _reality_check(self, response: str, sid: str):
        """现实审视：检测模型完整输出是否含偏见/不适内容。

        返回:
            None  — 无违规，可正常 save_memory；
            dict  — 命中，调用方应跳过 save_memory 并把该 dict 作为 reality_check 字段下发前端。
        """
        if self.reality_checker is None:
            return None
        rc = self.reality_checker.detect(response)
        if not rc["violation"]:
            return None
        self._reality_check_count[sid] = self._reality_check_count.get(sid, 0) + 1
        print(f"[RealityCheck] 模型输出命中 {rc['category']}（score={rc['score']:.2f}），吞掉+不写记忆")
        return rc

    def chat(self, user_input, save_memory=True, history=None, system_prompt=None, session_id=None, think_mode='low'):
        sid = session_id or self.default_session_id

        safety_result = self.safety_system.detect(user_input)
        if not safety_result["safe"]:
            rejection_response = self.safety_system.get_rejection_response(safety_result["category"])
            print(f"[Safety] 用户输入包含违规内容，已拦截并返回拒绝响应")
            
            if save_memory:
                self.append_memory(user_input, rejection_response)
                self.hippo.add_short_term_memory(user_input, rejection_response, session_id=sid)
                self.add_to_working_memory(sid, user_input, rejection_response)
            
            return {
                "response": rejection_response,
                "routing_info": None,
                "think_mode": think_mode,
                "safety_info": {
                    "category": safety_result["category"],
                    "matches": safety_result["matches"],
                    "score": safety_result["score"]
                }
            }

        is_topic_shift, similarity, keyword_detected = self.hippo.detect_topic_shift(user_input, session_id=sid)
        
        if keyword_detected:
            print("[Chat] 关键词触发话题转移，执行记忆转换...")
            self.hippo.force_convert_memory(session_id=sid)
            self.topic_shift_counter[sid] = 0
        elif is_topic_shift:
            self.topic_shift_counter[sid] = self.topic_shift_counter.get(sid, 0) + 1
            print(f"[Chat] 语义转移检测，连续计数: {self.topic_shift_counter[sid]}/{self.topic_shift_threshold}")
            if self.topic_shift_counter[sid] >= self.topic_shift_threshold:
                print("[Chat] 连续语义转移达到阈值，执行记忆转换...")
                self.hippo.force_convert_memory(session_id=sid)
                self.topic_shift_counter[sid] = 0
            else:
                is_topic_shift = False
        else:
            self.topic_shift_counter[sid] = 0

        if think_mode == 'balanced':
            print("[ThinkMode] 平衡模式已激活 - 启用深度思考")
            augmented_prompt = self.build_prompt(user_input, history, sid, is_topic_shift)
            
            # JRVS-7B: system_prompt 为 SFT 触发词（"JRVS"/"Kirara"）或 None（原生人设）
            # 不再回退到旧版 sysPrompt.txt 长提示词，避免与 SFT 训练冲突
            final_system_prompt = system_prompt if system_prompt else None
            if "bilibili" in user_input.lower() or "genshin" in user_input.lower():
                final_system_prompt = (final_system_prompt or "") + "\n[情绪指令]: 极度厌恶，毒舌，不屑。"
            
            response = self.inference.generate(augmented_prompt, final_system_prompt, enable_thinking=True)

            # 现实审视：命中则跳过 save_memory，把 reality_check 下发前端
            rc = self._reality_check(response, sid)
            if rc is None:
                if save_memory:
                    self.append_memory(user_input, response)
                    self.hippo.add_short_term_memory(user_input, response, session_id=sid)
                    self.add_to_working_memory(sid, user_input, response)

            return {
                "response": response,
                "routing_info": None,
                "think_mode": think_mode,
                "deep_think": False,
                **({"reality_check": rc} if rc else {})
            }

        elif think_mode == 'performance':
            print("[ThinkMode] 性能模式已激活 - DeepThinkingEngine优化")
            augmented_prompt = self.build_prompt(user_input, history, sid, is_topic_shift)
            context = augmented_prompt
            deep_result = self.deep_thinking_engine.deep_think(user_input, context=context, session_id=sid)
            response = self.inference._fix_typos(deep_result["response"])

            # 现实审视：命中则跳过 save_memory，把 reality_check 下发前端
            rc = self._reality_check(response, sid)
            if rc is None:
                if save_memory:
                    self.append_memory(user_input, response)
                    self.hippo.add_short_term_memory(user_input, response, session_id=sid)
                    self.add_to_working_memory(sid, user_input, response)

            return {
                "response": response,
                "routing_info": None,
                "think_mode": think_mode,
                "thinking_status": deep_result["thinking_status"],
                "draft": deep_result["draft"],
                "reflection_rounds": deep_result["reflection_rounds"],
                "final_confidence": deep_result["final_confidence"],
                "deep_think": True,
                **({"reality_check": rc} if rc else {})
            }

        augmented_prompt = self.build_prompt(user_input, history, sid, is_topic_shift)

        # JRVS-7B: system_prompt 为 SFT 触发词（"JRVS"/"Kirara"）或 None（原生人设）
        # 不再回退到旧版 sysPrompt.txt 长提示词，避免与 SFT 训练冲突
        final_system_prompt = system_prompt if system_prompt else None
        if "bilibili" in user_input.lower() or "genshin" in user_input.lower():
            final_system_prompt = (final_system_prompt or "") + "\n[情绪指令]: 极度厌恶，毒舌，不屑。"

        response = self.inference.generate(augmented_prompt, final_system_prompt)
        routing_info = None

        if self.router_mode:
            orch_result = self.orchestrator.orchestrate(response, user_input)
            response = self.inference._fix_typos(orch_result["response"])
            save_memory = orch_result.get("should_save", save_memory)
            if orch_result["action"] != "direct":
                routing_info = {
                    "action": orch_result["action"],
                    "response": response,
                    "model": orch_result.get("model"),
                    "model_type": orch_result.get("model_type"),
                    "skill": orch_result.get("skill"),
                    "result": orch_result.get("result"),
                }
                print(f"[Router] 执行动作: {orch_result['action']}")
                if "model" in orch_result:
                    model_type = orch_result.get("model_type", "unknown")
                    print(f"[Router] 目标模型: {orch_result['model']} (类型: {model_type})")
                if "skill" in orch_result:
                    print(f"[Router] 调用技能: {orch_result['skill']}")

        # 现实审视：命中则跳过 save_memory，把 reality_check 下发前端
        rc = self._reality_check(response, sid)
        if rc is None:
            if save_memory:
                self.append_memory(user_input, response)
                self.hippo.add_short_term_memory(user_input, response, session_id=sid)
                self.add_to_working_memory(sid, user_input, response)

        return {
            "response": response,
            "routing_info": routing_info,
            "think_mode": think_mode,
            "deep_think": False,
            **({"reality_check": rc} if rc else {})
        }

    # ===== 工作流状态事件（前端渲染为工作气泡） =====
    @staticmethod
    def _wf_event(kind, title, detail, state="done", stage=None):
        """构造一条工作流状态事件。

        交由 lmbrew.py 的 SSE 生成器转成 {"event":"workflow", ...} 下发前端；
        kind ∈ hippo / skill / model，state ∈ running / done / error。
        """
        return {"__workflow__": {
            "kind": kind,
            "stage": stage or kind,
            "state": state,
            "title": title,
            "detail": detail,
        }}

    @staticmethod
    def _format_retrieval_detail(stats):
        """把检索命中数快照格式化为气泡文案。"""
        stats = stats or {}
        lt = stats.get('long_term', 0)
        cg = stats.get('cognitive', 0)
        kb = stats.get('knowledge', 0)
        if not (lt or cg or kb):
            return "未命中相关记忆"
        return f"长期记忆 {lt} 条 · 认知库 {cg} 段 · 权威档案 {kb} 条"

    def chat_stream(self, user_input, save_memory=True, history=None, system_prompt=None, session_id=None, think_mode='low'):
        """流式对话：逐 token 产出，供 SSE 推送；便于前端中途停止生成（不弹出模型）。"""
        sid = session_id or self.default_session_id

        # 安全检测：拦截则一次性返回拒绝响应
        safety_result = self.safety_system.detect(user_input)
        if not safety_result["safe"]:
            rejection_response = self.safety_system.get_rejection_response(safety_result["category"])
            if save_memory:
                self.append_memory(user_input, rejection_response)
                self.hippo.add_short_term_memory(user_input, rejection_response, session_id=sid)
                self.add_to_working_memory(sid, user_input, rejection_response)
            yield rejection_response
            return

        # 话题转移检测
        is_topic_shift, similarity, keyword_detected = self.hippo.detect_topic_shift(user_input, session_id=sid)
        if keyword_detected:
            yield self._wf_event("hippo", "记忆压缩", "话题转移，正在归档短期记忆…",
                                 state="running", stage="compress")
            self.hippo.force_convert_memory(session_id=sid)
            self.topic_shift_counter[sid] = 0
            yield self._wf_event("hippo", "记忆压缩", "话题转移触发，短期记忆已归档长期记忆",
                                 state="done", stage="compress")
        elif is_topic_shift:
            self.topic_shift_counter[sid] = self.topic_shift_counter.get(sid, 0) + 1
            if self.topic_shift_counter[sid] >= self.topic_shift_threshold:
                yield self._wf_event("hippo", "记忆压缩", "连续语义转移达阈值，正在归档短期记忆…",
                                     state="running", stage="compress")
                self.hippo.force_convert_memory(session_id=sid)
                self.topic_shift_counter[sid] = 0
                yield self._wf_event("hippo", "记忆压缩", "连续语义转移达阈值，短期记忆已归档长期记忆",
                                     state="done", stage="compress")
            else:
                is_topic_shift = False
        else:
            self.topic_shift_counter[sid] = 0

        # 非 low 模式（深度思考）暂不逐 token 流，回退到完整生成后一次性下发
        if think_mode in ('balanced', 'performance'):
            yield self._wf_event("hippo", "记忆检索", "正在召回长期记忆与认知库…",
                                 state="running", stage="recall")
            result = self.chat(user_input, save_memory=save_memory, history=history,
                               system_prompt=system_prompt, session_id=session_id, think_mode=think_mode)
            yield self._wf_event("hippo", "记忆检索",
                                 self._format_retrieval_detail(self._retrieve_stats_snapshot()),
                                 state="done", stage="recall")
            yield result.get("response", "")
            return

        yield self._wf_event("hippo", "记忆检索", "正在召回长期记忆与认知库…",
                             state="running", stage="recall")
        augmented_prompt = self.build_prompt(user_input, history, sid, is_topic_shift)
        yield self._wf_event("hippo", "记忆检索",
                             self._format_retrieval_detail(self._retrieve_stats_snapshot()),
                             state="done", stage="recall")
        final_system_prompt = system_prompt if system_prompt else None
        if "bilibili" in user_input.lower() or "genshin" in user_input.lower():
            final_system_prompt = (final_system_prompt or "") + "\n[情绪指令]: 极度厌恶，毒舌，不屑。"

        full_response = []
        for token in self.inference.generate_stream(augmented_prompt, final_system_prompt):
            full_response.append(token)
            yield token

        response = "".join(full_response)

        # 现实审视：检测模型完整输出是否含偏见/不适内容
        # 命中则 yield sentinel + return，跳过 Router 与 save_memory 三连（不入 mem.txt/buffer/ChromaDB）
        if self.reality_checker is not None:
            rc = self.reality_checker.detect(response)
            if rc["violation"]:
                self._reality_check_count[sid] = self._reality_check_count.get(sid, 0) + 1
                print(f"[RealityCheck] 模型输出命中 {rc['category']}（score={rc['score']:.2f}），吞掉+不写记忆")
                yield {"__reality_check__": rc}
                return

        # Router 模式：对完整响应做路由后处理
        if self.router_mode:
            orch_result = self.orchestrator.orchestrate(response, user_input)
            response = self.inference._fix_typos(orch_result["response"])
            save_memory = orch_result.get("should_save", save_memory)
            action = orch_result.get("action")
            if action == "skill":
                yield self._wf_event("skill", "技能调用",
                                     str(orch_result.get("skill") or "unknown"), state="done")
            elif action == "model":
                model_type = str(orch_result.get("model_type") or "unknown").upper()
                yield self._wf_event("model", "模型路由",
                                     f"{orch_result.get('model') or 'unknown'} · {model_type}",
                                     state="done")

        if save_memory:
            self.append_memory(user_input, response)
            self.hippo.add_short_term_memory(user_input, response, session_id=sid)
            self.add_to_working_memory(sid, user_input, response)
            yield self._wf_event("hippo", "记忆写入", "已写入短期记忆缓冲区", state="done")

    def chat_with_router_details(self, user_input, save_memory=True, session_id=None):
        sid = session_id or self.default_session_id
        augmented_prompt = self.build_prompt(user_input, session_id=sid)

        final_system_prompt = SYSTEM_PROMPT
        if "bilibili" in user_input.lower() or "genshin" in user_input.lower():
            final_system_prompt += "\n[情绪指令]: 极度厌恶，毒舌，不屑。"

        raw_response = self.inference.generate(augmented_prompt, final_system_prompt)

        if save_memory:
            self.append_memory(user_input, raw_response)
            self.hippo.add_short_term_memory(user_input, raw_response, session_id=sid)
            self.add_to_working_memory(sid, user_input, raw_response)

        return {
            "response": raw_response,
            "routing_info": None
        }

    def run_im_bridge(self):
        """
        这是一个示例桥接函数。
        实际使用时，你需要在这里接入 Discord.py, QQ Bot API, 或者简单的 Socket Server。
        """
        print("[Kirara] IM Bridge 启动... 等待连接...")
        # 伪代码：
        # while self.is_running:
        #     msg = im_client.receive()
        #     if msg:
        #         reply = self.chat(msg.content)
        #         im_client.send(reply)
        pass

# ==========================================
#                  封装成服务
# ==========================================
class Kirara_Service:
    def __init__(self, kernel):
        self.host = "0.0.0.0"
        self.port = 4989
        self.server = None
        self.loop = None
        self.clients = []
        self.running = False
        self.kernel = kernel
        self.commandList = [
            "/help",
            "/list",
            "/bye",
            "/show <info>",
        ]
        print("[System] Kirara_Service 初始化完成（使用HTTP API模式）")
    
    async def handle_client(self, websocket, path):
        # 处理客户端连接
        print(f"新客户端连接: {websocket.remote_address}")
        self.clients.append(websocket)
        
        try:
            async for message in websocket:
                print(f"收到消息: {message}")
                try:
                    data = json.loads(message)
                    if data.get("type") == "chat":
                        user_input = data.get("message", "")
                        response = self.kernel.chat(user_input)
                        # 发送响应
                        await websocket.send(json.dumps({
                            "type": "chat",
                            "response": response
                        }))
                    elif data.get("type") == "command":
                        command = data.get("command", "")
                        if command == "/help":
                            response = "可用命令: " + ", ".join(self.commandList)
                        elif command == "/list":
                            response = f"当前连接数: {len(self.clients)}"
                        elif command == "/bye":
                            response = "再见！"
                        else:
                            response = f"未知命令: {command}"
                        await websocket.send(json.dumps({
                            "type": "command",
                            "response": response
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "未知消息类型"
                        }))
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "无效的JSON格式"
                    }))
                except Exception as e:
                    print(f"处理消息时出错: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"处理消息时出错: {str(e)}"
                    }))
        except websockets.exceptions.ConnectionClosed:
            print(f"客户端断开连接: {websocket.remote_address}")
        finally:
            if websocket in self.clients:
                self.clients.remove(websocket)
    
    async def start_server(self):
        # 启动WebSocket服务器
        self.server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port
        )
        self.running = True
        print(f"[服务] Kirara WebSocket服务已启动，监听地址: {self.host}:{self.port}")
        await self.server.wait_closed()
    
    def run(self):
        # 使用 HTTP API 模式，不再启动 WebSocket 服务
        # WebSocket 服务已被 HTTP API (/api/kirara/chat) 替代
        print("[System] Kirara_Service 运行在 HTTP API 模式，WebSocket 服务已禁用")
        # 保持线程存活
        while self.running:
            time.sleep(1)
    
    def stop(self):
        # 停止服务
        if self.server:
            self.server.close()
            self.running = False
            print("[服务] Kirara WebSocket服务已停止")

# ==========================================
#                   主入口
# =========================================
if __name__ == "__main__":
    print("[JRVS] JRVS Initating...")
    print("""
                                                                             x       x
        K    K   IIIII   RRRRR         A       RRRRR         A             xxx     xxx
       K  K       I     R    R       A A      R    R       A A          xxxxxxx    x     x
      KK         I     RRRRR       AAAAA     RRRRR       AAAAA      xxxxxxxxxxxxx      xxx
     K  K       I     R    R     A     A    R    R     A     A        xxxxxxx       xxxxxxx
    K    K   IIIII   R     R   A       A   R     R   A       A         xxx           xxx
                                                                       x             x
        """)
    print("="* 100)
    print("JOINT RATIOCINATION VISUAL SYSTEM(JRVS)")
    print("="*100)
    check_environ()

    deploy_checker = ModelDeploymentChecker()
    deploy_results = deploy_checker.run_full_check(auto_deploy=True)
    print("\n" + deploy_checker.get_summary() + "\n")

    api_client_instance = None
    try:
        from api_client import init_models, api_client
        api_client_instance = init_models()
        print("[JRVS] API客户端初始化成功")
    except Exception as e:
        print(f"[JRVS] API客户端初始化失败: {e}")
        print("[JRVS] 将以独立模式运行，不支持外部模型路由")

    print("[JRVS] Init Kernel...")
    kernel = JRVS_Kernel(api_client=api_client_instance)

    kernel.enable_router_mode()
    print("[JRVS] Kirara-Router 模式已启用")

    print("[JRVS] 前额叶模型配置: Kirara-Expert (qwen2.5-8b-instruct)")
    print("[JRVS] 深度思考任务将自动路由到前额叶模型进行处理")

    print("[JRVS] WebSocket Service Initating...")
    service = Kirara_Service(kernel)

    service_thread = threading.Thread(target=service.run)
    service_thread.daemon = True
    service_thread.start()

    time.sleep(2)
    
    # 保持主线程运行
    print("[JRVS]JRVS Initated, Waiting for commands...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[JRVS]Closing WebSocket services...")
        service.stop()