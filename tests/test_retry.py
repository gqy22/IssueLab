"""测试重试机制"""

import pytest

from issuelab.retry import RetryError, retry_async, retry_sync


class TestRetryAsync:
    """测试异步重试机制"""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """第一次尝试成功"""
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_async(succeed, max_retries=3)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_success_after_retries(self):
        """重试后成功"""
        call_count = 0

        async def succeed_on_third():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"

        result = await retry_async(succeed_on_third, max_retries=3, initial_delay=0.1)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        """所有重试都失败"""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(RetryError):
            await retry_async(always_fail, max_retries=2, initial_delay=0.1)

        assert call_count == 3  # 1 initial + 2 retries


class TestRetrySync:
    """测试同步重试机制"""

    def test_decorator_success(self):
        """装饰器：成功情况"""
        call_count = 0

        @retry_sync(max_retries=3, initial_delay=0.1)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeed()
        assert result == "success"
        assert call_count == 1

    def test_decorator_retry_then_succeed(self):
        """装饰器：重试后成功"""
        call_count = 0

        @retry_sync(max_retries=3, initial_delay=0.1)
        def succeed_on_second():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Not yet")
            return "success"

        result = succeed_on_second()
        assert result == "success"
        assert call_count == 2

    def test_decorator_all_fail(self):
        """装饰器：所有重试失败"""
        call_count = 0

        @retry_sync(max_retries=2, initial_delay=0.1)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(RetryError):
            always_fail()

        assert call_count == 3  # 1 initial + 2 retries

    def test_backoff_timing(self):
        """测试退避延迟"""
        import time

        call_times = []

        @retry_sync(max_retries=2, initial_delay=0.1, backoff_factor=2.0)
        def track_timing():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Retry")
            return "success"

        track_timing()

        # 验证延迟递增
        assert len(call_times) == 3
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay2 > delay1  # 第二次延迟应该更长
