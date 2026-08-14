# V6 Object Storage Security Review

This document evaluates the security posture and constraints of the newly implemented Object Storage (MinIO/S3) backend for Abast-GP V6.0, as we prepare for production deployment.

## 1. Bucket Privacy
- **Finding**: All object storage buckets must be strictly **private**.
- **Rule**: Public access is explicitly forbidden.
- **Enforcement**: No bucket policies allowing `s3:GetObject` or `s3:PutObject` anonymously should exist. All access must be brokered via the FastAPI backend using authenticated Presigned URLs or internal AWS SDKs (boto3) initialized with restricted service account credentials.

## 2. Presigned URL Expiration
- **Finding**: Presigned URLs issued for `/v2/documents/upload/initiate` grant direct write access to the bucket.
- **Rule**: Short-lived expiration must be enforced.
- **Enforcement**: URLs are generated with a strict `ExpiresIn` parameter of 3600 seconds (1 hour). If the upload does not complete within this window, the URL becomes invalid and the document state transitions to `EXPIRED`.

## 3. CORS Configuration
- **Finding**: Browsers interacting directly with MinIO/S3 via Presigned URLs will enforce CORS policies.
- **Rule**: CORS must be restricted to the exact domain(s) of the frontend application.
- **Enforcement**: The object storage provider must be configured with a CORS rule allowing `PUT` methods, but strictly limiting `AllowedOrigins` to the production frontend domain (e.g., `https://app.abast-gp.com`). Wildcards (`*`) are prohibited in production.

## 4. Tenant Isolation
- **Finding**: Multi-tenancy must be enforced at the storage layer to prevent data cross-contamination.
- **Rule**: Objects must be logically separated by `tenant_id`.
- **Enforcement**: The Object Storage Strategy uses prefixes for physical separation: `{tenant_id}/{document_id}`. This ensures that even if a token is compromised, the backend logic prevents generating presigned URLs for a tenant ID that the user does not belong to.

## 5. SHA256 Integrity Verification
- **Finding**: Files uploaded via presigned URLs bypass the backend during transit.
- **Rule**: File integrity and repudiation prevention must be guaranteed.
- **Enforcement**: The `/v2/documents/upload/complete` endpoint requires a SHA-256 hash from the client. The backend compares this against the MinIO/S3 object's ETag or explicitly computes it if necessary. Any mismatch immediately transitions the document to the `FAILED` state.

## 6. Least Privilege IAM
- **Finding**: The backend API and the OCR worker have different access requirements.
- **Rule**: IAM roles must follow the principle of least privilege.
- **Enforcement**:
  - **API Service Account**: Requires `s3:PutObject` (for presigned URL generation) and `s3:GetObject` (for validation).
  - **OCR Worker Service Account**: Requires `s3:GetObject` (to download the source file) and `s3:PutObject` (to upload artifacts). It does *not* need permissions to delete objects or modify bucket configurations.
