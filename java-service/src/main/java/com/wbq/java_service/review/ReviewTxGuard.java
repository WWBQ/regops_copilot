package com.wbq.java_service.review;

import org.springframework.stereotype.Component;

@Component
public class ReviewTxGuard {
    public void afterWrite() {
        // 测试可替换此 Bean，在审计写入后抛错以证明整笔事务回滚。
    }
}
