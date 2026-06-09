"""
Vanna exceptions - 已精简 (2026-06 清理)

只保留 ValidationError (vanna_client 真实使用)
已删除 6 个未用: DependencyError / ImproperlyConfigured / ConnectionError / OTPCodeError / SQLRemoveError / ExecutionError / APIError
"""


class ValidationError(Exception):
    """数据/参数验证错误"""
    pass
