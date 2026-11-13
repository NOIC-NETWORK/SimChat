import os
import json
import time
import datetime
import base64
import io
import mimetypes
from typing import Any, Dict, List, Optional
from simchat_mod import BaseSkill, ToolSpec, hook



UPLOAD_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

VISION_MODEL_CANDIDATES = ["llava", "moondream", "bakllava", "llava:7b", "llava:13b"]
_default_vision_model = None
SUPPORTED_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"]
MAX_IMAGE_SIZE = 20 * 1024 * 1024
SUPPORTED_RESOLUTIONS = {
    "sd": (640, 360),
    "hd": (1280, 720),
    "fhd": (1920, 1080),
    "original": None
}

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[ScreenshotRecognition] Pillow 未安装，截图功能不可用")

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("[ScreenshotRecognition] ollama 未安装，图像识别功能不可用")


def _image_to_base64(image_path: str) -> Optional[str]:
    try:
        with open(image_path, "rb") as f:
            img_data = f.read()
        return base64.b64encode(img_data).decode("utf-8")
    except Exception as e:
        print(f"[ScreenshotRecognition] 图片转Base64失败: {e}")
        return None


def _resize_image(image_path: str, max_resolution: str = "hd") -> Optional[str]:
    if not PIL_AVAILABLE:
        return None

    try:
        img = Image.open(image_path)
        target_size = SUPPORTED_RESOLUTIONS.get(max_resolution)

        if target_size and img.size != target_size:
            img = img.resize(target_size, Image.LANCZOS)

        if img.mode == "RGBA":
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)

        temp_path = os.path.join(UPLOAD_DIR, f"resized_{int(time.time())}.jpg")
        with open(temp_path, "wb") as f:
            f.write(buffer.read())

        return temp_path
    except Exception as e:
        print(f"[ScreenshotRecognition] 图片缩放失败: {e}")
        return None


def _capture_screenshot(region: Optional[tuple] = None, resolution: str = "original") -> Optional[str]:
    if not PIL_AVAILABLE:
        return None

    try:
        if region:
            screenshot = ImageGrab.grab(bbox=region)
        else:
            screenshot = ImageGrab.grab()

        if resolution != "original" and resolution in SUPPORTED_RESOLUTIONS:
            target_size = SUPPORTED_RESOLUTIONS[resolution]
            if target_size and screenshot.size != target_size:
                screenshot = screenshot.resize(target_size, Image.LANCZOS)

        if screenshot.mode == "RGBA":
            screenshot = screenshot.convert("RGB")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(UPLOAD_DIR, f"screenshot_{timestamp}.jpg")
        screenshot.save(file_path, "JPEG", quality=92)

        print(f"[ScreenshotRecognition] 截图已保存: {file_path}")
        return file_path
    except Exception as e:
        print(f"[ScreenshotRecognition] 截图失败: {e}")
        return None


def _get_default_vision_model() -> str:
    global _default_vision_model
    if _default_vision_model:
        return _default_vision_model

    if not OLLAMA_AVAILABLE:
        return VISION_MODEL_CANDIDATES[0]

    try:
        models_list = ollama.list()
        existing_models = set()
        if models_list and "models" in models_list:
            for model_info in models_list["models"]:
                name = model_info.get("name", "")
                existing_models.add(name.split(":")[0])
                existing_models.add(name)

        for candidate in VISION_MODEL_CANDIDATES:
            if candidate in existing_models or candidate.split(":")[0] in existing_models:
                _default_vision_model = candidate
                print(f"[ScreenshotRecognition] 自动检测到视觉模型: {candidate}")
                return candidate

        _default_vision_model = VISION_MODEL_CANDIDATES[0]
        print(f"[ScreenshotRecognition] 未检测到视觉模型，默认使用: {_default_vision_model}")
        return _default_vision_model
    except Exception as e:
        print(f"[ScreenshotRecognition] 检测视觉模型失败: {e}")
        _default_vision_model = VISION_MODEL_CANDIDATES[0]
        return _default_vision_model


def list_available_vision_models() -> Dict[str, Any]:
    if not OLLAMA_AVAILABLE:
        return {"success": False, "error": "ollama 未安装"}

    try:
        models_list = ollama.list()
        vision_models = []
        if models_list and "models" in models_list:
            for model_info in models_list["models"]:
                name = model_info.get("name", "")
                if any(candidate.split(":")[0] in name for candidate in VISION_MODEL_CANDIDATES):
                    vision_models.append({
                        "name": name,
                        "size": model_info.get("size", 0),
                        "modified": model_info.get("modified_at", "")
                    })

        return {
            "success": True,
            "vision_models": vision_models,
            "recommended": VISION_MODEL_CANDIDATES,
            "default": _get_default_vision_model()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _recognize_with_ollama(image_path: str, prompt: str = "请识别图片中的所有文字内容，并描述图片的主要内容。", model: str = "") -> Dict[str, Any]:
    if not OLLAMA_AVAILABLE:
        return {"success": False, "error": "ollama 未安装"}

    if not model:
        model = _get_default_vision_model()

    try:
        base64_img = _image_to_base64(image_path)
        if not base64_img:
            return {"success": False, "error": "图片读取失败"}

        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64_img]
                }
            ],
            options={
                "temperature": 0.3,
                "top_p": 0.9,
                "num_ctx": 4096
            }
        )

        recognized_text = response.get("message", {}).get("content", "")

        return {
            "success": True,
            "recognized_text": recognized_text,
            "model_used": model,
            "image_path": image_path
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "no such" in error_msg.lower():
            return {
                "success": False,
                "error": f"视觉模型 '{model}' 未安装。请运行: ollama pull {model}",
                "hint": "推荐的视觉模型: llava, moondream, bakllava"
            }
        return {"success": False, "error": f"Ollama 识别失败: {error_msg}"}


def _get_image_info(image_path: str) -> Dict[str, Any]:
    if not os.path.exists(image_path):
        return {"exists": False, "error": "文件不存在"}

    try:
        file_size = os.path.getsize(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = mimetypes.guess_type(image_path)[0] or "image/unknown"

        info = {
            "exists": True,
            "name": os.path.basename(image_path),
            "path": image_path,
            "size": file_size,
            "size_formatted": _format_file_size(file_size),
            "extension": ext,
            "mime_type": mime_type
        }

        if PIL_AVAILABLE:
            try:
                img = Image.open(image_path)
                info["width"], info["height"] = img.size
                info["format"] = img.format
                info["mode"] = img.mode
                img.close()
            except Exception:
                pass

        return info
    except Exception as e:
        return {"exists": False, "error": str(e)}


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class ScreenshotRecognitionSkill(BaseSkill):
    skill_name = "screenshotRecognition"
    skill_description = "截图识别技能：支持屏幕截图、图片上传识别，基于视觉模型进行文字识别和内容分析"
    skill_version = "1.0.0"
    trigger_keywords = [
        "截图", "截屏", "识别", "图片识别", "文字识别", "OCR",
        "screenshot", "recognize", "image", "picture", "photo",
        "看图", "读图", "屏幕截图", "抓取屏幕",
        "截个屏", "截个图", "帮我截", "截一下", "拍个屏",
        "看看图", "看一下图", "图片文字", "提取文字", "图片里",
        "视觉模型", "模型列表"
    ]
    input_schema = {
        "action": str,
        "image_path": str,
        "prompt": str,
        "region": dict,
        "resolution": str,
        "model": str
    }

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        action = params.get("action", "")
        image_path = params.get("image_path", "")
        prompt = params.get("prompt", "请识别图片中的所有文字内容，并描述图片的主要内容。")
        model = params.get("model", "")

        if not action:
            if image_path:
                action = "recognize"
            else:
                action = "capture_and_recognize"

        if action == "capture":
            return self._handle_capture(params)
        elif action == "recognize":
            return self._handle_recognize(image_path, prompt, model)
        elif action == "capture_and_recognize":
            capture_result = self._handle_capture(params)
            if not capture_result.get("success"):
                return capture_result
            captured_path = capture_result.get("image_path", "")
            return self._handle_recognize(captured_path, prompt, model)
        elif action == "info":
            return self._handle_info(image_path)
        elif action == "list_models":
            return list_available_vision_models()
        else:
            return {"success": False, "error": f"未知操作: {action}", "supported_actions": ["capture", "recognize", "capture_and_recognize", "info", "list_models"]}

    def _handle_capture(self, params: Dict[str, Any]) -> Dict[str, Any]:
        region = params.get("region")
        resolution = params.get("resolution", "original")

        if region:
            try:
                x1 = int(region.get("x1", 0))
                y1 = int(region.get("y1", 0))
                x2 = int(region.get("x2", 1920))
                y2 = int(region.get("y2", 1080))
                region_tuple = (x1, y1, x2, y2)
            except (ValueError, TypeError):
                return {"success": False, "error": "区域参数格式错误，应为 {x1, y1, x2, y2}"}
        else:
            region_tuple = None

        image_path = _capture_screenshot(region=region_tuple, resolution=resolution)
        if not image_path:
            return {"success": False, "error": "截图失败，请检查 Pillow 是否正确安装"}

        image_info = _get_image_info(image_path)
        return {
            "success": True,
            "action": "capture",
            "image_path": image_path,
            "image_info": image_info
        }

    def _handle_recognize(self, image_path: str, prompt: str, model: str) -> Dict[str, Any]:
        if not image_path:
            return {"success": False, "error": "未提供图片路径，请使用 action=capture 截图或提供 image_path"}

        if not os.path.exists(image_path):
            return {"success": False, "error": f"图片不存在: {image_path}"}

        file_size = os.path.getsize(image_path)
        if file_size > MAX_IMAGE_SIZE:
            resized_path = _resize_image(image_path, max_resolution="hd")
            if resized_path:
                image_path = resized_path
            else:
                return {"success": False, "error": f"图片过大 ({_format_file_size(file_size)})，最大支持 {_format_file_size(MAX_IMAGE_SIZE)}"}

        image_info = _get_image_info(image_path)
        recognition_result = _recognize_with_ollama(image_path, prompt, model)

        if recognition_result.get("success"):
            return {
                "success": True,
                "action": "recognize",
                "image_info": image_info,
                "recognized_text": recognition_result["recognized_text"],
                "model_used": recognition_result["model_used"]
            }
        else:
            return recognition_result

    def _handle_info(self, image_path: str) -> Dict[str, Any]:
        if not image_path:
            return {"success": False, "error": "未提供图片路径"}
        info = _get_image_info(image_path)
        return {
            "success": True,
            "action": "info",
            "image_info": info
        }

    def list_captures(self, limit: int = 20) -> Dict[str, Any]:
        captures = []
        if os.path.exists(UPLOAD_DIR):
            for fname in sorted(os.listdir(UPLOAD_DIR), reverse=True):
                if fname.startswith("screenshot_") or fname.startswith("resized_"):
                    fpath = os.path.join(UPLOAD_DIR, fname)
                    if os.path.isfile(fpath):
                        captures.append(_get_image_info(fpath))
                        if len(captures) >= limit:
                            break
        return {"success": True, "captures": captures, "count": len(captures)}

    def delete_capture(self, file_name: str) -> Dict[str, Any]:
        file_path = os.path.join(UPLOAD_DIR, file_name)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return {"success": True, "message": f"截图 {file_name} 已删除"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "文件不存在"}


def init_screenshotRecognition_skill():
    manager = get_skill_manager()
    registry = manager.get_registry()

    existing = registry.get_skill("screenshotRecognition")
    if existing:
        print("[ScreenshotRecognition] screenshotRecognition 技能已注册")
        return existing

    skill = ScreenshotRecognitionSkill()
    registry.register_skill(skill)
    print("[ScreenshotRecognition] screenshotRecognition 技能初始化完成")
    return skill


if __name__ == "__main__":
    print("[ScreenshotRecognition] 初始化截图识别技能...")
    skill = init_screenshotRecognition_skill()

    print("\n[ScreenshotRecognition] 功能列表:")
    print("  action=capture              - 全屏截图")
    print("  action=recognize            - 识别指定图片")
    print("  action=capture_and_recognize - 截图并立即识别")
    print("  action=info                - 查看图片信息")
    print("  action=list_models         - 查看可用视觉模型")

    print("\n[ScreenshotRecognition] 示例使用:")
    print('  manager = get_skill_manager()')
    print('  result = manager.execute_skill("screenshotRecognition", {"action": "capture_and_recognize"})')
    print('  result = manager.execute_skill("screenshotRecognition", {"action": "capture", "region": {"x1": 100, "y1": 100, "x2": 800, "y2": 600}})')
    print('  result = manager.execute_skill("screenshotRecognition", {"action": "recognize", "image_path": "/path/to/screenshot.jpg"})')
    print('  result = manager.execute_skill("screenshotRecognition", {"action": "list_models"})')
    print('  result = manager.auto_execute("帮我截个屏并识别一下")')

# ----- 工具实例 -----
_instance = ScreenshotRecognitionSkill()


def execute(params):
    return _instance.execute(params)


@hook("agent.tool")
def register(api):
    api.register_tool(ToolSpec(
        name="screenshotRecognition",
        label="screenshotRecognition",
        description=_instance.skill_description,
        risk="read",
        usage="screenshotRecognition PARAMS: ...",
        input_schema=_instance.input_schema,
        triggers=_instance.trigger_keywords,
        backend="screenshotRecognition:execute",
    ))