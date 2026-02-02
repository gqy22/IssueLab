"""测试 __main__ 模块功能"""
from issuelab.__main__ import truncate_text, MAX_COMMENT_LENGTH


class TestTruncateText:
    """测试文本截断功能"""
    
    def test_short_text_not_truncated(self):
        """短文本不应被截断"""
        text = "Short text"
        result = truncate_text(text)
        assert result == text
        assert "已截断" not in result
    
    def test_exact_limit_not_truncated(self):
        """刚好达到限制不截断"""
        text = "a" * MAX_COMMENT_LENGTH
        result = truncate_text(text)
        assert len(result) == MAX_COMMENT_LENGTH
        assert "已截断" not in result
    
    def test_long_text_truncated(self):
        """超长文本被截断"""
        text = "a" * (MAX_COMMENT_LENGTH + 1000)
        result = truncate_text(text)
        assert len(result) <= MAX_COMMENT_LENGTH
        assert "已截断" in result
    
    def test_truncate_at_paragraph(self):
        """在段落边界截断"""
        # 创建带多个段落的文本
        paragraphs = ["段落" + str(i) + "\n\n" for i in range(100)]
        text = "".join(paragraphs) * 100  # 确保超出限制
        
        result = truncate_text(text, max_length=1000)
        assert len(result) <= 1000
        assert "已截断" in result
    
    def test_custom_max_length(self):
        """自定义最大长度"""
        text = "a" * 1000
        result = truncate_text(text, max_length=100)
        assert len(result) <= 100
        assert "已截断" in result
    
    def test_truncate_preserves_encoding(self):
        """截断保持中文编码"""
        text = "中文测试" * 5000
        result = truncate_text(text, max_length=1000)
        assert len(result) <= 1000
        # 验证结果仍然是有效的字符串
        assert isinstance(result, str)
