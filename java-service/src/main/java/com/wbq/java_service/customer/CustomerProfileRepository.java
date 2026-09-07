package com.wbq.java_service.customer;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerProfileRepository extends JpaRepository<CustomerProfile, Long> {
    List<CustomerProfile> findAllByOrderByCompanyCodeAsc();

    Optional<CustomerProfile> findByPublicId(UUID publicId);
}
