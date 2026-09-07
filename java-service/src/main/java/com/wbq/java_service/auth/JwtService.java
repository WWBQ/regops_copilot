package com.wbq.java_service.auth;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jose.crypto.MACVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.wbq.java_service.config.AppProperties;
import com.wbq.java_service.identity.AppUser;
import com.wbq.java_service.identity.Role;

import org.springframework.stereotype.Service;

@Service
public class JwtService {

    private final byte[] secret;
    private final long ttlSeconds;

    public JwtService(AppProperties properties) {
        this.secret = padSecret(properties.auth().jwtSecret());
        this.ttlSeconds = properties.auth().ttlSeconds();
    }

    public String issue(AppUser user) {
        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .subject(user.getUsername())
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(ttlSeconds)))
                .claim("uid", user.getPublicId().toString())
                .claim("name", user.getDisplayName())
                .claim("email", user.getEmail())
                .claim("role", user.getRole().name())
                .claim("dept", user.getDept())
                .build();
        SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
        try {
            jwt.sign(new MACSigner(secret));
        } catch (JOSEException ex) {
            throw new IllegalStateException("签发 JWT 失败", ex);
        }
        return jwt.serialize();
    }

    public AuthUser parse(String token) {
        try {
            SignedJWT jwt = SignedJWT.parse(token);
            if (!jwt.verify(new MACVerifier(secret))) {
                return null;
            }
            JWTClaimsSet claims = jwt.getJWTClaimsSet();
            Date exp = claims.getExpirationTime();
            if (exp == null || exp.toInstant().isBefore(Instant.now())) {
                return null;
            }
            Role role = Role.valueOf(claims.getStringClaim("role"));
            return new AuthUser(
                    UUID.fromString(claims.getStringClaim("uid")),
                    claims.getSubject(),
                    claims.getStringClaim("name"),
                    claims.getStringClaim("email"),
                    role,
                    claims.getStringClaim("dept"),
                    "",
                    true
            );
        } catch (Exception ex) {
            return null;
        }
    }

    private static byte[] padSecret(String secret) {
        byte[] raw = secret.getBytes(StandardCharsets.UTF_8);
        if (raw.length >= 32) {
            return raw;
        }
        byte[] padded = new byte[32];
        System.arraycopy(raw, 0, padded, 0, raw.length);
        return padded;
    }
}
