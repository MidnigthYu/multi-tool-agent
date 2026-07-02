"""全局统一错误码枚举 -- 与架构文档完全对齐，共五大类。
格式: E{类别编号}{序号}
- E01xx: 模型异常
- E02xx: 工具超时
- E03xx: 文件解析失败
- E04xx: 存储异常
- E05xx: 会话失效
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """全局统一错误码，格式 E{类别}{序号}，共五大类。"""

    # === 第一类：模型异常 (E01xx) ===
    E0101 = "E0101"
    E0102 = "E0102"
    E0103 = "E0103"
    E0104 = "E0104"
    E0105 = "E0105"
    E0106 = "E0106"
    E0107 = "E0107"
    # === 第二类：工具超时 (E02xx) ===
    E0201 = "E0201"
    E0202 = "E0202"
    E0203 = "E0203"
    E0204 = "E0204"
    E0205 = "E0205"
    E0206 = "E0206"
    E0207 = "E0207"
    E0208 = "E0208"
    E0209 = "E0209"
    # === 第三类：文件解析失败 (E03xx) ===
    E0301 = "E0301"
    E0302 = "E0302"
    E0303 = "E0303"
    E0304 = "E0304"
    E0305 = "E0305"
    E0306 = "E0306"
    E0307 = "E0307"
    # === 第四类：存储异常 (E04xx) ===
    E0401 = "E0401"
    E0402 = "E0402"
    E0403 = "E0403"
    E0404 = "E0404"
    E0405 = "E0405"
    E0406 = "E0406"
    E0407 = "E0407"
    # === 第五类：会话失效 (E05xx) ===
    E0501 = "E0501"
    E0502 = "E0502"
    E0503 = "E0503"
    E0504 = "E0504"
    E0505 = "E0505"

    @staticmethod
    def to_http_status(code: ErrorCode) -> int:
        _http_map: dict[str, int] = {"E01": 502, "E02": 504, "E03": 422, "E04": 500, "E05": 400}
        return _http_map.get(code.value[:3], 500)

    @staticmethod
    def to_user_message(code: ErrorCode) -> str:
        _user_messages: dict[ErrorCode, str] = {
            ErrorCode.E0101: "模型响应超时，请稍后重试",
            ErrorCode.E0102: "模型服务暂时不可用，请稍后重试",
            ErrorCode.E0103: "主模型繁忙，已自动切换备用模型，回复质量可能略有下降",
            ErrorCode.E0104: "所有模型暂时不可用，请稍后重试",
            ErrorCode.E0105: "模型返回异常，请重新提问",
            ErrorCode.E0106: "当前会话过长，已自动压缩历史上下文",
            ErrorCode.E0107: "模型服务认证失败，请联系管理员",
            ErrorCode.E0201: "搜索超时，请尝试缩小搜索范围",
            ErrorCode.E0202: "搜索服务暂时不可用，将基于已有知识回答",
            ErrorCode.E0203: "代码执行超时，请检查代码是否存在死循环",
            ErrorCode.E0204: "工具执行超时，已跳过该步骤",
            ErrorCode.E0205: "工具多次重试失败，已跳过该步骤",
            ErrorCode.E0206: "沙箱容器启动失败，请检查 Docker 服务状态",
            ErrorCode.E0207: "高危代码已被拦截，系统调用、网络操作等行为不允许",
            ErrorCode.E0208: "代码执行崩溃，请检查运行时异常",
            ErrorCode.E0209: "代码执行输出超过字符上限，已自动截断",
            ErrorCode.E0301: "不支持的文件格式，请上传 PDF/Word/Excel 文件",
            ErrorCode.E0302: "文件过大，请上传小于 50MB 的文件",
            ErrorCode.E0303: "PDF 文件无法解析，请检查文件是否损坏或加密",
            ErrorCode.E0304: "Word 文档解析失败，请检查文件格式",
            ErrorCode.E0305: "Excel 文件解析失败，请检查文件格式",
            ErrorCode.E0306: "文件上传中断，请重新上传",
            ErrorCode.E0307: "文件内容为空，请上传包含文字内容的文件",
            ErrorCode.E0401: "向量数据库连接失败，请联系管理员",
            ErrorCode.E0402: "向量存储异常，文档索引已跳过",
            ErrorCode.E0403: "向量检索超时，请稍后重试",
            ErrorCode.E0404: "会话数据库异常，历史记录暂时不可用",
            ErrorCode.E0405: "存储空间不足，请联系管理员",
            ErrorCode.E0406: "文件读取失败，请联系管理员",
            ErrorCode.E0407: "数据目录创建失败，请联系管理员",
            ErrorCode.E0501: "会话已过期，请刷新页面重新开始",
            ErrorCode.E0502: "会话冲突，请稍后重试",
            ErrorCode.E0503: "会话状态丢失，请刷新页面重新开始",
            ErrorCode.E0504: "会话恢复失败，请刷新页面重新开始",
            ErrorCode.E0505: "上下文过长，已自动压缩早期内容",
        }
        return _user_messages.get(code, "未知错误，请联系管理员")
