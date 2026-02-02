"""测试日志配置"""
import logging
import tempfile
from pathlib import Path
from issuelab.logging_config import setup_logging, get_logger


def test_setup_logging_console_only():
    """测试仅控制台日志"""
    logger = setup_logging(level="DEBUG")
    
    assert logger.name == "issuelab"
    # logger 本身没有 level，检查 root logger
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
    
    # 检查至少有一个 handler
    assert len(root_logger.handlers) > 0


def test_setup_logging_with_file():
    """测试带文件日志"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        logger = setup_logging(level="INFO", log_file=log_file)
        
        # 写入日志
        logger.info("Test message")
        
        # 验证文件创建
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content


def test_get_logger():
    """测试获取命名 logger"""
    logger = get_logger("test_module")
    
    assert logger.name == "issuelab.test_module"
    assert isinstance(logger, logging.Logger)


def test_custom_format():
    """测试自定义格式"""
    custom_format = "%(levelname)s - %(message)s"
    logger = setup_logging(level="INFO", format_string=custom_format)
    
    # 验证 logger 正常工作
    logger.info("Custom format test")
    assert logger.name == "issuelab"


def test_multiple_setup_calls():
    """测试多次调用 setup_logging"""
    logger1 = setup_logging(level="INFO")
    logger2 = setup_logging(level="DEBUG")
    
    # 应该返回相同的 logger 实例
    assert logger1.name == logger2.name
    
    # 级别应该被更新
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
