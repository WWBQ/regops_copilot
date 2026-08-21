package com.wbq.java_service.dto.documents;

public record ViewerUrlResponse(
        String docId,
        Integer page,
        Integer expiresIn,
        String viewerUrl
) {
}
