package com.wbq.java_service.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    @Bean
    RestClient pythonRestClient(AppProperties properties) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofMillis(properties.pythonAi().connectTimeoutMs()));
        requestFactory.setReadTimeout(Duration.ofMillis(properties.pythonAi().readTimeoutMs()));

        return RestClient.builder()
                .baseUrl(properties.pythonAi().baseUrl())
                .requestFactory(requestFactory)
                .build();
    }
}
